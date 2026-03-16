import json
import urllib.request
import urllib.error
import os
import re
from datetime import datetime
from math import degrees, atan2, acos
from utils.load_data import load_sensor


class FastAPIHandler:
    def __init__(self, url):
        self.url = url

    def _prepare_payload(self, addr, filename, local_dir, fft_result):
        path = os.path.join(local_dir, filename)
        if not os.path.exists(path):
            return "FILE NOT FOUND"
        
        data = load_sensor(path)
        if not data:
            return None

        meta = data['metadata']
        summ = data['summary']
        samples = data['samples']

        axis = meta['axis'].replace("_axis", "").replace("axis", "").strip()
        fs_value = meta['fs']
        sensitivity = meta['sensitivity']

        # gestione timestamp con regex
        match = re.search(r'(\d{2}_\d{2}_\d{4}_\d{2}_\d{2}_\d{2})', filename)
        ts = datetime.strptime(match.group(1), '%d_%m_%Y_%H_%M_%S') if match else datetime.now()

        # Calcoli Fisici
        m1, m2, m3 = summ["rms_x"], summ["rms_y"], summ["rms_z"]
        accrms = (m1**2 + m2**2 + m3**2)**0.5
        phi = degrees(atan2(m2, m1))
        theta = degrees(acos(m3 / accrms)) if accrms != 0 else 0
        
        current_rms = {"X": m1, "Y": m2, "Z": m3}.get(axis, 0.0)

        # Picchi fft
        current_fft = fft_result.get(meta['axis'], {})
        freq_peaks = [current_fft.get(f"peak_freq_{i}", 0.0) for i in range(1, 5)]
        mags_peaks = [current_fft.get(f"max_mag_{i}", 0.0) for i in range(1, 5)]

        # payload
        return {
            "mac": addr,
            "timestamp": ts.isoformat(),
            "asse": axis,
            "fs": fs_value,
            "sensitivity": sensitivity,
            "metriche": {
                "temp": summ['temperature'],
                "humidity": summ.get("humidity", 0.0),
                "phi": phi,
                "theta": theta,
                "rms_asse": current_rms,
                "fft_freqs": freq_peaks,
                "fft_mags": mags_peaks
            },
            "samples": samples
        }




    def upload_file(self, addr, files_to_send, local_dir, fft_result, logger_callback):
        if not files_to_send:
            return

        uploaded_successfully = []
        for filemame in list(files_to_send):
            payload = self._prepare_payload(addr, filemame, local_dir, fft_result)

            if payload == "FILE NOT FOUND":
                logger_callback(f"\t[FastAPI][WARN] File {filemame} rimosso\n")
            if payload:
                try:
                    data_json = json.dumps(payload).encode('utf-8')
                    req = urllib.request.Request(
                        url=self.url,
                        data=data_json,
                        headers={'Content-Type': 'application/json'},
                        method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=40) as response:
                        if response.status == 200:
                            logger_callback(f"\t[FastAPI] OK. {filemame} salvato con MAC {addr}\n")
                            uploaded_successfully.append(filemame)
                except Exception as e:
                    logger_callback(f"\t[FastAPI][ERRORE] {str(e)}")
                    
        return uploaded_successfully