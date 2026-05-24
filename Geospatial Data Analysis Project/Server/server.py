import os
import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import ipaddress
from flask import Flask, request, jsonify
from flask_cors import CORS

# ─── Configuration ─────────────────────────────────────────────────────────────
BASE_PATH = './Server/Data'
PERIOD = 1800  # 30-minute bins

# ─── Data Loading & Precomputation ─────────────────────────────────────────────
# Read all .parquet shards in parallel
dataset = ds.dataset(BASE_PATH, format="parquet")
df = dataset.to_table().to_pandas()

# Precompute uint32 representations of IP floats
df['ip_first_uint']  = df['ip_first'].view(np.uint32)
df['ip_second_uint'] = df['ip_second'].view(np.uint32)

# Pre-bin timestamps
df['ts_bin'] = (df['timestamp'] // PERIOD).astype(np.int64)

# ─── Helper Functions ──────────────────────────────────────────────────────────
def filter_df(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    df_f = df

    # Protocol filter
    proto_raw = f.get('ip_protocol')
    if proto_raw and proto_raw.lower() != 'all':
        if proto_raw.lower() == 'other':
            df_f = df_f[~df_f['ip_protocol'].isin([1, 6, 17])]
        else:
            try:
                p = int(proto_raw)
            except ValueError:
                p = {'icmp':1, 'tcp':6, 'udp':17}.get(proto_raw.lower())
            df_f = df_f[df_f['ip_protocol'] == p]

    # IP / additional_ip filters
    for key in ('ip', 'additional_ip'):
        ip_str = f.get(key)
        if ip_str:
            try:
                u = int(ipaddress.IPv4Address(ip_str))
                df_f = df_f[
                    (df_f['ip_first_uint']  == u) |
                    (df_f['ip_second_uint'] == u)
                ]
            except ipaddress.AddressValueError:
                pass

    # anomaly_score threshold
    thr = f.get('anomaly_score')
    if thr is not None:
        try:
            t = float(thr)
            df_f = df_f[df_f['anomaly_score'] >= t]
        except ValueError:
            pass

    return df_f


def compute_geo_summaries(df_f: pd.DataFrame):
    # Nodes
    n1 = df_f[['lat_first','long_first','anomaly_score']].rename(
        columns={'lat_first':'lat','long_first':'lon'}
    )
    n2 = df_f[['lat_second','long_second','anomaly_score']].rename(
        columns={'lat_second':'lat','long_second':'lon'}
    )
    nodes = pd.concat([n1, n2], ignore_index=True)
    node_grp = nodes.groupby(['lat','lon'], as_index=False).agg(
        count=('anomaly_score','size'),
        max_anomaly=('anomaly_score','max')
    )
    node_list = node_grp[['lat','lon','count','max_anomaly']].values.tolist()

    # Edges
    a1, o1 = df_f['lat_first'].values, df_f['long_first'].values
    a2, o2 = df_f['lat_second'].values, df_f['long_second'].values
    scores   = df_f['anomaly_score'].values

    mask = (a1 < a2) | ((a1 == a2) & (o1 <= o2))
    from_lat = np.where(mask, a1, a2)
    from_lon = np.where(mask, o1, o2)
    to_lat   = np.where(mask, a2, a1)
    to_lon   = np.where(mask, o2, o1)

    edges = pd.DataFrame({
        'from_lat':     from_lat,
        'from_lon':     from_lon,
        'to_lat':       to_lat,
        'to_lon':       to_lon,
        'anomaly_score': scores
    })
    edge_grp = edges.groupby(
        ['from_lat','from_lon','to_lat','to_lon'], as_index=False
    ).agg(
        count=('anomaly_score','size'),
        max_anomaly=('anomaly_score','max')
    )
    edge_list = edge_grp[['from_lat','from_lon','to_lat','to_lon','count','max_anomaly']].values.tolist()

    return node_list, edge_list


def compute_statistics(df_f: pd.DataFrame):
    if df_f.empty:
        return None, [], []
    bins = df_f['ts_bin']
    counts = bins.value_counts(sort=False)
    mx     = df_f.groupby('ts_bin')['anomaly_score'].max()
    start_ts = int(bins.min()) * PERIOD
    end_bin  = int(bins.max())
    rng = range(int(bins.min()), end_bin + 1)
    flow_counts    = [int(counts.get(b, 0)) for b in rng]
    anomaly_scores = [float(mx.get(b, 0))    for b in rng]
    return start_ts, flow_counts, anomaly_scores

# ─── Flask App ────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, origins="http://127.0.0.1:8000")


@app.route('/filtered_data', methods=['POST'])
def filtered_data():
    f = request.json or {}
    df_f = filter_df(df, f)
    start_ts, counts, scores = compute_statistics(df_f)
    nodes, edges = compute_geo_summaries(df_f)

    return jsonify({
        'nodes': nodes,
        'edges': edges,
        'statistics': {
            'start_timestamp': start_ts,
            'flow_counts':     counts,
            'anomaly_scores':  scores,
            'period':          PERIOD
        }
    })


@app.route('/selected_data', methods=['POST'])
def selected_data():
    payload = request.json or []
    if not (isinstance(payload, list) and len(payload) == 5):
        return jsonify([])

    lat1, lon1, lat2, lon2, f = payload
    df_f = filter_df(df, f)
    if df_f.empty:
        return jsonify([])

    if lat2 == -1 and lon2 == -1:
        mask = (
            ((df_f['lat_first']  == lat1) & (df_f['long_first']  == lon1)) |
            ((df_f['lat_second'] == lat1) & (df_f['long_second'] == lon1))
        )
    else:
        mask = (
            ((df_f['lat_first']  == lat1) & (df_f['long_first']  == lon1) &
             (df_f['lat_second'] == lat2) & (df_f['long_second'] == lon2)) |
            ((df_f['lat_first']  == lat2) & (df_f['long_first']  == lon2) &
             (df_f['lat_second'] == lat1) & (df_f['long_second'] == lon1))
        )

    df_edges = df_f[mask]
    if df_edges.empty:
        return jsonify([])

    grp = df_edges.groupby(
        ['ip_first_uint','ip_second_uint'], as_index=False
    ).agg(
        count=('anomaly_score','size'),
        max_anomaly=('anomaly_score','max')
    ).sort_values('max_anomaly', ascending=False)

    selected = []
    for _, row in grp.iterrows():
        u1, u2 = int(row['ip_first_uint']), int(row['ip_second_uint'])
        selected.append({
            'from_ip':       str(ipaddress.IPv4Address(u1)),
            'to_ip':         str(ipaddress.IPv4Address(u2)),
            'count':         int(row['count']),
            'anomaly_score': float(row['max_anomaly'])
        })

    return jsonify(selected)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
