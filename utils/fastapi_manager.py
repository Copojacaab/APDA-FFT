import json
import urllib.request
import urllib.error
import os
import re
from datetime import datetime
from math import degrees, atan2, acos
from utils.load_data import load_sensor


class FastAPIHandler:
    def __init__(self, url, client_id, client_secret, registration_token):
        self.url = url
        self.client_id = client_id
        self.client_secret = client_secret
        self.reg_token = registration_token
        self.token = None

    def register(self, logger_callback):
        """
            Esegue l'onboarding del gateway presso l'API
        """    
        clean_url = self.url.strip().rstrip('/')
        base_url = clean_url.rsplit('/', 1)[0]
        registration_url = f"{base_url}/register"
    
        # Debug: aggiungi una stampa per vedere l'URL esatto nei log
        logger_callback(f"\t[DEBUG] Tentativo di registrazione su: {registration_url}\n")
        payload = {
            "client_id": self.client_id,
            "registration_token": self.reg_token
        }

        try:
            data_json = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                url=registration_url,
                data=data_json,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    res_body = json.loads(response.read().decode('utf-8'))
                    # API restituisce client_secret
                    new_secret = res_body.get('client_secret')
                    if new_secret:
                        self.client_secret = new_secret
                        logger_callback(f"\t[FASTAPI]Registrazione completata con successo (client_secret ricevuta)")
                        return new_secret       #OUT POSITIVO
                
        except urllib.error.HTTPError as e:
            error_content = e.read().decode('utf-8')
            logger_callback(f"\t[FASTAPI][Err REG] Errore API ({e.code}): {error_content}")
        except Exception as e:
            logger_callback(f"\t[FASTAPI][Err REG] Errore connessione durante registration: {str(e)}")

        return None
    

    def get_new_token(self, logger_callback):
        """
            Richiede un nuovo JWT 
        """
        # Ricostruzione endpoint
        base_url = self.url.rsplit('/', 1)[0]
        token_url = f"{base_url}/token"
        
        auth_payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        try:
            data_json = json.dumps(auth_payload).encode('utf-8')
            req = urllib.request.Request(
                url = token_url,
                data = data_json,
                headers = {'Content-Type': 'application/json'},
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status == 200:
                    res_body = json.loads(response.read().decode('utf-8'))
                    self.token = res_body.get("access_token")
                    logger_callback(f"\t[FASTAPI] Sessione autenticata: nuovo token JWT")
                    return True
        except Exception as e:
            logger_callback(f"\t[FASTAPI][Err AUTH] Login fallito: {str(e)}")
            return False
        
        
        
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
        """
            Invia i file gestendo autonomamente la validita del token
        """
        if not files_to_send:
            return

        # 1. Handshake
        if not self.token:
            if not self.get_new_token(logger_callback):
                return []
            
        uploaded_successfully = []
        for filemame in list(files_to_send):
            payload = self._prepare_payload(addr, filemame, local_dir, fft_result)

            if not payload or payload == "FILE NOT FOUND":
                continue
            # Gestione Retry: se il token scade (401) riprovo una volta
            for attempt in range(2):
                try:
                    data_json = json.dumps(payload).encode('utf-8')
                    headers = {
                        'Content-Type': 'application/json',
                        'Authorization': f'Bearer {self.token}'
                    }
                    
                    req = urllib.request.Request(
                        url=self.url,
                        data=data_json,
                        headers=headers,
                        method='POST'
                    )
                    with urllib.request.urlopen(req, timeout=120) as response:
                        if response.status == 200:
                            logger_callback(f"\t[FastAPI] OK. {filemame} salvato con MAC {addr}\n")
                            uploaded_successfully.append(filemame)
                            break
            
                except urllib.error.HTTPError as e:
                    # Se il srv risponde con 401 => token scaduto
                    if e.code == 401 and attempt == 0:
                        logger_callback("\t[FASTAPI] Token scaduto. Avvio retry automatico...\n")
                        if self.get_new_token(logger_callback):
                            continue
                    
                    logger_callback(f"\t[FastAPI][ERRORE] {filemame}: {str(e)}")
                    break # -> retry loop, continue to the next file
                except Exception as e:
                    logger_callback(f"\t[FASTAPI][CRITICAL] Errore imprevisto: {str(e)}")
                    break
                    
        return uploaded_successfully