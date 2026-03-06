import urllib.request
import urllib.error
import time
import os
from datetime import datetime
from math import degrees, atan2, sqrt, acos

from utils.load_data import load_sensor


"""
    utils.influxdb_manager:
    Responsabile dell'invio dei dati a InfluxDB tramite API HTTP,
    Distingue due tipi di informazioni per ogni sensore:
        - WS_Summary: metadati e statische aggregate (temp, RMS, angoli, res_ftt)
        - Ws_Samples: campioni sensore accellerometrico (associato al timestamp)

    Note:
    ------  
    - Cleaunup dei file dalla memoria fatto in ftp_manger.py (influx => ftp => cleanup)
"""
class InfluxHandler:
    
    def __init__(self, url, token, local_dir):
        self.url = url                          #http://localhost:8086/api/v2/write?org=wise&bucket=SHM_Data&precision=ms
        self.token = token
        self.local_dir = local_dir
        

    
    """
        Creazione del payload influxdb per un singolo file e invio a influx 
        Params:
            - addr: MAC
            - filename: nome del file da processare
            - fft_result: dizionario con i risultati dell'analisi FFT (peak_freq, max_mag)
        Returns: 
            - status: stringa di successo o errore
    """
    def _create_and_send(self, addr, filename, fft_result):
        path = os.path.join(self.local_dir, filename)
        
        try:
            # Parser log del sensore
            data = load_sensor(path)                #stesso parser dell'fft
            if not data:
                return f"Errore: file {filename} non valido o mancante"
            
            meta, summ, samples = data["metadata"], data["summary"], data["samples"]
            date_part = "_".join(filename.split("_")[2:5])
            timestamp_base = datetime.strptime(date_part + ' ' + meta["timestamp"], '%d_%m_%Y %H:%M:%S')
            utime_base_ms = int(time.mktime(timestamp_base.timetuple()) * 1000)

            # --- Calcoli Fisici (RMS e Angoli) ---
            m1, m2, m3 = summ["rms_x"], summ["rms_y"], summ["rms_z"]
            accrms = sqrt(m1**2 + m2**2 + m3**2)
            phi = degrees(atan2(m2, m1))
            theta = degrees(acos(m3 / accrms)) if accrms != 0 else 0

            # 1. Costruzione tabella summary (WS_Summary)
            summary_payload = (
                "WS_Summary,id={addr},axis={axis} "
                "temp={temp},rms_x={rx},rms_y={ry},rms_z={rz},phi={phi},theta={theta},"
                "pf={pf},mm={mm},range=\"{ar}\",sync={sync} {utime}"
            ).format(
                addr=addr, axis=meta["axis"], temp=summ["temperature"],
                rx=m1, ry=m2, rz=m3, phi=phi, theta=theta,
                pf=fft_result.get('peak_freq', -1), mm=fft_result.get('max_mag', -1),
                ar=meta["sensitivity"], sync=meta["is_synced"], utime=utime_base_ms
            )

            # 2. Preparazione tabella samnples (WS_Samples)
            sample_lines = []
            for i, d in enumerate(samples):
                utime = utime_base_ms + int((i / meta["fs"]) * 1000)
                sample_lines.append(f"WS_Samples,id={addr},axis={meta['axis']} data={d} {utime}")

            # 3. Invio a Batch
            # unisco la riga summary al primo batch per efficienza
            all_data = [summary_payload] + sample_lines
            batch_size = 500

            headers = {'Authorization': f'Token {self.token}', 'Content-Type': 'text/plain; charset=utf-8'}

            for i in range(0, len(all_data), batch_size):
                batch = "\n".join(all_data[i : i + batch_size])
                req = urllib.request.Request(self.url, data=batch.encode('utf-8'), headers=headers, method='POST')
                # Spedizione POST a Influx
                with urllib.request.urlopen(req, timeout=20) as response:
                    if response.status != 204:
                        return f"Errore HTTP {response.status} al batch {i//batch_size}"

            return f"OK: {filename} ({len(samples)} campioni) "

        except Exception as e:
            return f"Errore: {str(e)}"



    """
        Punto di ingresso chiamato dal gateway. Gestisce la coda dei file da inviare
    """
    def upload_influx_data(self, addr, files_to_send, fft_result, logger_callback):
        if not files_to_send:
            return 
        
        # Loop sui file da inviare:
        # creo una copia della lista (per ciclare)
        # lavoro sulla lista originale (per remove)
        for filename in list(files_to_send):
            status = self._create_and_send(addr, filename, fft_result)
            logger_callback(f"\t[Influx] {status}\n")
            files_to_send.remove(filename)