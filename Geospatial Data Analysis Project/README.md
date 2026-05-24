HOW TO RUN THIS CODE:
1. Put the parquet data files in Server/Data
2. Navigate to the current directory in terminal
3. Run this command in the terminal: python3 Server/server.py 
4. Run this command in the terminal in a different terminal: python3 -m http.server 8000
5. Navigate to this url in a browser: http://127.0.0.1:8000/
6. Close the terminal or terminate the process to stop the server

INSTRUCTIONS:<br>
Click a point to reveal a list of from_ip, to_ip, count, and anomaly score<br>
Click a edge to reveal a list of from_ip, to_ip, count, and anomaly score<br>
Modify filter settings to show only certain nodes and edges. This also shows the statistics graph<br>

TOOLS (top right): <br>
Magnifying glass - enter and go to landmark or address <br>
Home - zoom out and go to North America<br>
Map - switch to 2D mode (or switch back to 3D)<br>
Imagery - switch the imagery of the globe<br>
Question Mark - shows how to navigate on the globe<br>

NOTE:<br>
With Internet Connection - Runs normally with precise map<br>
Without Internet Connection - Click the fourth button in the top right. Then click Natural Earth II. This map is less precise<br>


