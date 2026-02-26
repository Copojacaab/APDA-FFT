
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

    # HEADER
    header = lines[0].strip().split(";")
    metadata["timestamp"] = header[0]
    metadata["sensitivity"] = header[1]
    metadata["fs"] = float(header[2].replace(" Hz", ""))
    metadata["axis"] = header[3]

    # skip della riga di sink

    # SUMMARY
    summary_line = lines[2].strip().split(";");
    summary["temperature"] = float(summary_line[0])
    summary["rms_x"] = float(summary_line[1])
    summary["rms_y"] = float(summary_line[2])
    summary["rms_z"] = float(summary_line[3])

    # CAMPIONI
    for line in lines[4:]:
        vals = line.strip().split(";")

        if (len(vals) < 4):
            continue
        
        for data in vals:
            try:
                samples.append(float(data))
            except ValueError:
                continue
    
    return {"metadata": metadata, "summary": summary, "samples": samples}

# data = load_sensor("data/0013a20041e7f6b7_Xaxis_2_11_22_18_20_32.log")
# # print("Frequenza di campionamento:", data["metadata"]["fs"])
# # print(len(data["samples"]))