import urllib.request
import urllib.error
import time
import os
from datetime import datetime
from math import degrees, atan2, sqrt, acos

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
            if not os.path.exists(path):
                return f"File {filename} non trovato"
            
            with open(path, 'r') as f:
                # Leggo l'header del file log del sensore
                parameters = f.readline().split(";")[:-1]
                type_of_sync = f.readline().strip().split(" ")[:-1]
                mean_values = f.readline().split(";")[:-1]
                f.readline() # Salto la riga "First values"
                data = f.readline().split(";")[:-1]
                data_float = [float(x) for x in data if x.strip()]

            # --- Calcoli Fisici (RMS e Angoli) ---
            m1, m2, m3 = float(mean_values[1]), float(mean_values[2]), float(mean_values[3])
            accrms = sqrt(pow(m1, 2) + pow(m2, 2) + pow(m3, 2))
            phi = degrees(atan2(m2, m1))
            theta = degrees(acos(m3 / accrms)) if accrms != 0 else 0
            
            timestamp_base = datetime.strptime(date + ' ' + parameters[0], '%d_%m_%Y %H:%M:%S')
            odr_val = float(parameters[2].replace(" Hz", ""))
            sync_bit = "1.0" if type_of_sync and type_of_sync[0] == "Synced" else "0.0"

            clean_axis = parameters[3].replace(" axis", "").replace(" ", "_")
            clean_range = parameters[1].replace(" ", "")

            res = []
            # Stringa base per InfluxDB (Line Protocol)
            base_str = (
                "WS_Test_Data,id={addr},axis={axis} "
                "acc_range=\"{ar}\",temperature={temp},rms_x={rx},rms_y={ry},rms_z={rz},"
                "phi={phi},theta={theta},issync={sync},peak_freq={pf},max_mag={mm},data={dat} {utime}"
            )

            for i, d in enumerate(data_float):
                # Calcolo il timestamp per ogni singolo campione basandomi sull'ODR
                utime = int((time.mktime(timestamp_base.timetuple()) + i / odr_val) * 1000)
                res.append(base_str.format(
                    addr=addr, axis=clean_axis, ar=clean_range,
                    temp=mean_values[0], rx=m1, ry=m2, rz=m3,
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