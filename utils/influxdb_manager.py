import urllib.request
import urllib.error
import time
import os
from datetime import datetime
from math import degrees, atan2, sqrt, acos

from utils.load_data import load_sensor
class InfluxHandler:
    def __init__(self, url, token, local_dir):
        self.url = url
        self.token = token
        self.local_dir = local_dir
        
    def upload_influx_data(self, addr, files_to_send, fft_result, logger_callback):
        if not files_to_send:
            return 
        
        # Uso una copia della lista così posso rimuovere gli elementi mentre ciclo
        for filename in list(files_to_send):
            status = self._create_and_send(addr, filename, fft_result)
            logger_callback(f"\t[Influx] {status}\n")
            files_to_send.remove(filename)
        
    def _create_and_send(self, addr, filename, fft_result):
        date = "_".join(filename.split("_")[2:5])
        path = os.path.join(self.local_dir, filename) 
        
        try:
            # Parser log del sensore
            data = load_sensor(path)
            if not data:
                return f"Errore: file {filename} non valido o mancante"
            
            meta = data["metadata"]
            summ = data["summary"]
            samples = data["samples"]

            # META
            date_part = "_".join(filename.split("_")[2:5])
            timestamp_base = datetime.strptime(date_part + ' ' + meta["timestamp"], '%d_%m_%Y %H:%M:%S')
            odr_val = meta["fs"]
            sync_bit = meta["is_synced"]

            clean_axis = meta["axis"]
            clean_range = meta["sensitivity"]


            # --- Calcoli Fisici (RMS e Angoli) ---
            m1, m2, m3 = summ["rms_x"], summ["rms_y"], summ["rms_z"]
            accrms = sqrt(m1**2 + m2**2 + m3**2)
            phi = degrees(atan2(m2, m1))
            theta = degrees(acos(m3 / accrms)) if accrms != 0 else 0

            # Stringa base per InfluxDB (Line Protocol)
            base_str = (
                "WS_Test_Data,id={addr},axis={axis} "
                "acc_range=\"{ar}\",temperature={temp},rms_x={rx},rms_y={ry},rms_z={rz},"
                "phi={phi},theta={theta},issync={sync},peak_freq={pf},max_mag={mm},data={dat} {utime}"
            )

            res = []
            for i, d in enumerate(samples):
                # Calcolo il timestamp per ogni singolo campione basandomi sull'ODR
                utime = int((time.mktime(timestamp_base.timetuple()) + i / odr_val) * 1000)
                res.append(base_str.format(
                    addr=addr, axis=clean_axis, ar=clean_range,
                    temp=summ["temperature"], rx=m1, ry=m2, rz=m3,
                    phi=phi, theta=theta, sync=sync_bit,
                    pf=fft_result.get('peak_freq', -1),
                    mm=fft_result.get('max_mag', -1),
                    dat=d, utime=utime
                ))
            


            payload = '\n'.join(res)
            headers = {'Content-Type': 'text/plain; charset=utf-8', 'Authorization': f'Token {self.token}'}
            req = urllib.request.Request(self.url, data=payload.encode('utf-8'), headers=headers, method='POST')
            
            # Spedizione POST a Influx
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 204:
                    return f"OK: {filename}"
                return f"Errore HTTP {response.status}"
            
        except Exception as e:
            return f"Errore: {str(e)}"
        