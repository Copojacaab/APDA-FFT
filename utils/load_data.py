import math

"""
{
    "metadata":{
        "timpestamp": "...",
        "sensitivity": "2g",
        "fs": 31.25
        "axis": "X"
    },
    "summary": {
        "temperature": 25.010,
        "rms_x": -0.0222,
        "rms_y": ...,
        ...
    },
    "samples": []
}
"""

def load_sensor(filepath):
    metadata = {}
    summary = {}
    samples = []

    with open(filepath, "r", encoding="utf-8") as file:
        lines = file.readlines()

    if len(lines) < 5:                  #verifica integrita' file
        return None
    
    # RIGA 0: HEADER
    header = lines[0].strip().split(";")
    metadata["timestamp"] = header[0]
    metadata["sensitivity"] = header[1].replace(" ", "")
    metadata["fs"] = float(header[2].replace(" Hz", ""))
    metadata["axis"] = header[3].replace(" axis", "").replace(" ", "_")

    # RIGA1: SYNC
    sync_raw = lines[1].strip().replace(";","")
    metadata["sync_type"] = sync_raw 
    metadata["is_synced"] = 1.0 if sync_raw in ["Synced", "Synced2"] else 0.0
    
    # RIGA2 2: SUMMARY
    summary_line = lines[2].strip().split(";");
    summary["temperature"] = float(summary_line[0])
    summary["rms_x"] = float(summary_line[1])
    summary["rms_y"] = float(summary_line[2])
    summary["rms_z"] = float(summary_line[3])

    # RIGA 3: FIRST_VALUES
    first_values_line = lines[3].strip().split(";")
    summary["first_x"] = float(first_values_line[0])
    summary["first_y"] = float(first_values_line[1])
    summary["first_z"] = float(first_values_line[2])

    # CAMPIONI
    for line in lines[4:]:
        vals = [v for v in line.strip().split(";") if v]
        if not vals: 
            continue
        
        for data in vals:
            try:
                num = float(data)
                # scarto se non e' finito (nan o inf)
                if math.isfinite(num):
                    samples.append(num)

            except ValueError:
                continue
    
    return {"metadata": metadata, "summary": summary, "samples": samples}

# data = load_sensor("data/0013a20041e7f6b7_Xaxis_2_11_22_18_20_32.log")
# # print("Frequenza di campionamento:", data["metadata"]["fs"])
# # print(len(data["samples"]))