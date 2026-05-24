import os
import pandas as pd
import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.ensemble import IsolationForest

# 1. Locate all parquet files
DATA_DIR = 'Server/Data'
parquet_files = sorted(
    os.path.join(DATA_DIR, f)
    for f in os.listdir(DATA_DIR)
    if f.endswith('.parquet')
)

# 2. Load all dataframes
dfs = [pd.read_parquet(p) for p in parquet_files]

# 3. Determine numeric columns (same for all)
num_cols = (
    dfs[0]
    .select_dtypes(include=[np.number])
    .columns
    .drop('anomaly_score', errors='ignore')
)

# 4. Stack for training
X = np.vstack([df[num_cols].values for df in dfs])

# 5. Impute missing values
imputer = SimpleImputer(strategy='mean')
X_imp = imputer.fit_transform(X)

# 6. Train Isolation Forest
clf = IsolationForest(
    n_estimators=100,
    contamination='auto',
    random_state=42
)
clf.fit(X_imp)

# 7. Compute raw anomaly scores (higher ⇒ more anomalous) and normalize [0,1]
raw = -clf.decision_function(X_imp)
min_s, max_s = raw.min(), raw.max()

# 8. Split scores back into each DataFrame and save
idx = 0
for df, path in zip(dfs, parquet_files):
    n = len(df)
    scores = raw[idx:idx + n]
    df['anomaly_score'] = (scores - min_s) / (max_s - min_s)
    df.to_parquet(path, index=False)
    print(f"Wrote scored data to {os.path.basename(path)}")
    idx += n
