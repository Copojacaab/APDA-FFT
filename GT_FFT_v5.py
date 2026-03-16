
import os
import cmath
import ctypes
import resource
from datetime import datetime, timezone
import time
import json
from math import degrees, atan2, sqrt, acos
import urllib.request
import urllib.error



"""
============================================
"""

from metrics.fft_iterativa import start_fft
from utils.load_data import load_sensor
from utils.get_peak_resolution import get_top_peaks_resolution
from utils.get_peak_prominence import get_top_peaks_prominence

from utils.ftp_manager import FTPClient
# from utils.influxdb_manager import InfluxHandler
from utils.fastapi_manager import FastAPIHandler
from protocol_decoder import ProtocolDecoder
from protocol_radio import XBeeManager

"""
============================================
"""

class Gateway:
    # --- COSTANTI DI CLASSE ---
    DATA_DIR =  '/etc/config/scripts/SHM_Data/'

    # Inizializzazione della classe Gateway().
    def __init__(self):
        
        # 1. dizionari di stato
        self.device_dict = {}                               #chi e' online?
        self.config_dict = {}                               #config di per ogni device
        self.fft_dict = {}                                  #risultati FFT

        # 2. coda di invio
        self.file2s_dict_ftp = {}                           #file da inviare al server
        # self.file2s_influx_dict = {}                        #file da inviare a influx
        self.file2s_fastapi_dict = {}

        # 3. gestione stream e buffer
        self.open_file_dict = {}                           #file aperti
        self.pack_num_dict = {}                             #numero pacchetto atteso
        self.first_data_dict = {}                           #baseline accellerometro
        
        # 4. variabilli di servizio
        self.original_payload = None
        self.delay = 0
        self.delay_time = 2
        self.t = datetime.now()

        # 5. caricamento config
        self.load_gateway_config()

        # 6. istanziazione handler
        self.ftp_handler = FTPClient(
            server=self.server_name,
            user=self.username,
            pwd=self.pwd,
            path=self.server_path,
            local_dir = self.DATA_DIR
        )
        
        # self.influx_handler = InfluxHandler(
        #     url=self.influx_url,
        #     token=self.influx_token,
        #     local_dir= self.DATA_DIR
        # )

        self.fastapi_handler = FastAPIHandler(
            url = self.fastapi_url
        )
        # 7. creo istanza modulo di connessione radio con i sensori
        self.xbee = XBeeManager(timeout=5)


    def run(self):
        """ Metodo per l'avvio operativo del gw """
        try:
            self.xbee.start(self.append_history)
            self.append_history(f"--- Gateway Start: {datetime.now()} ---\n\n")

            # reset file sensori
            with open(self.device_file, 'w+') as f:
                pass

            # LOOP principale di ascolto
            while True:
                self.main()

        except Exception as e:
            self.append_history(f"ERRORE CRITICO ESECUZIONE: {e}\n")
        finally:
            self.xbee.stop(self.append_history)

    # HELPER FUNCTIONS
    def load_gateway_config(self, config_path = "/etc/config/scripts/gw_config.json"): 
        
        self.logger_file = '/etc/config/scripts/SHM_Data/history.log'           # percorso provvisorio per gestire errori iniziali
        try:
            with open(config_path, 'r') as file:
                config = json.load(file)
                
                # parametri FTP
                self.server_name = config['ftp']['server']
                self.username = config['ftp']['user']
                self.pwd = config['ftp']['pwd']
                self.server_path = config['ftp']['path']
                
                # parametri influx
                # self.influx_url = config['influxdb']['url']
                # self.influx_token = config['influxdb']['token']

                # parametri fastapi
                self.fastapi_url = config['fastapi']['url']
                
                # percorsi file e impostazioni gateway
                self.logger_file = config['gateway']['logger_file']
                self.device_file = config['gateway']['device_file']
                self.config_file = config['gateway']['config_file']
                self.is_flexibile_structure = config['gateway'].get('is_flexibile_structure', True)
                
                print("Configurazione caricata con successo")
        except Exception as e: 
            # in caso di errore fermo esecuzione 
            self.append_history(f"ERRORE CRITICO nel caricamento della configurazione: {e}")
            exit(1)

    def _process_stream_data(self, payload_slice, addr, first_value=0, is_append=False):
        """
            Metodo unificato per pipeline di decodifica e scrittura dei campioni su file.


            Args:
                payload_slice: fetta del payload da decodificare (list)
                addr: MAC(string)
                first_value: valore di baseline per offset
                is_append: True => append al file esistente; False => crea un nuovo file (default False)

            Returns:
                acq_data: (list(str)) campioni decodificati
            Raises:
                errori loggati tramite append_history()

            Example:
                #in process_mid_stream
                acq_data = self._process_stream_data(payload[3:], addr, self.first_data_dict.get(addr, 0), is_append=True)
        """
        
        try:
            # 1. decodifica
            acq_data = ProtocolDecoder.decode_samples(payload_slice, first_value)

            # 2. scrivo nel file(se esiste un file aperto per il dispositivo)
            if addr in self.open_file_dict and os.path.exists(self.open_file_dict[addr]):
                file_path = self.open_file_dict[addr]
                mode = 'a' if is_append else 'w+'                       #append o scrivi nuovo

                try:
                    with open(file_path, mode) as f:
                        for d in acq_data:
                            f.write(d + ';')
                except IOError as e:
                    self.append_history(f"\t [ERROR] impossibile scrivere su file {file_path}: {str(e)}")
                    return acq_data     #restituisci comunque i dati
            else:
                self.append_history(f"\t[WARN] tentativo di scrivere su file chiuso o inesistente per sensore {addr}")
            
            return acq_data
        except Exception as e:
            self.append_history(f"\t[ERROR] Errore in _process_data_stream per {addr}: {str(e)}")
            return []

    # Aspetta di ricevere un pacchetto dati sul canale impostato nel gateway, da qualunque fonte.
    # I valori restituiti sono il payload e l'indirizzo del dispositivo che ha trasmesso i dati.
    # def get_data(self):
    #     """
    #     The function `get_data` reads data from a device, extracts the payload and address, and handles
    #     exceptions by logging errors.
    #     :return: The `get_data` method returns a tuple containing `list_pl` and `addr`. If an exception
    #     is caught during the execution of the method, it will return `None, None`. If the exception
    #     message contains the word "timeout", it will also return `None, None` without logging the error.
    #     """
    #     try:
    #         xbee_message = self.device.read_data(timeout=5)
    #         if xbee_message is None:
    #             return None, None
    #         self.remote_device = xbee_message.remote_device
    #         if hasattr(xbee_message.remote_device, 'get_64bit_addr'):
    #             addr = str(xbee_message.remote_device.get_64bit_addr()).lower()
    #         else:
    #             addr = str(xbee_message.remote_device).lower()
    #         pl = xbee_message.data
    #         list_pl = list(pl)
    #         self.t = datetime.now()
    #         self.original_payload = pl
    #         return list_pl, addr
    #     except Exception as e:
    #         # Se il messaggio di errore contiene "timeout", ignora e non loggare
    #         if "timeout" in str(e).lower():
    #             return None, None
    #         # Altri errori vengono loggati
    #         self.append_history("\tErrore in get_data: %s\n" % str(e))
    #         return None, None


    def check_device_config(self):
        """
            Apre il file di configurazione dei sensori (/scripts/config.txt) e
            e mappa addr => parametri_sensore
        """
        with open(self.config_file, 'r') as c:
            lines = c.readlines()               # Legge tutte le righe insieme.
            for line in lines:                  # Analizza una riga per volta.
                config_address = line[:16]      # MAC
                config_parameters = line[17:]   # Parametri (range, ODR, asse, soglie si shock)
                self.config_dict[config_address] = config_parameters.strip() 

    # Processa il payload ricevuto, in base al primo byte del pacchetto.
    # 0xA1 = sincronizzazione;
    # 0xD1 = inizio di stream di dati;
    # 0xD2 = continuazione dello stream di dati;
    # 0xD3 = fine stream di dati;
    # 0xD4 = dati ridotti (errore nella memoria del sensore che ha trasmesso i dati);
    # 0xC1 = dati di un evento sopra la soglia 1 e sotto la soglia 2;
    # ?    = tipo di pacchetto non riconosciuto.
    def process_data(self, payload, addr):
        packet_type = payload[0]    # Identifica il tipo di pacchetto ricevuto.

        if packet_type == 0xa1:
            self.process_sync_data(payload, addr)
        elif packet_type == 0xd1:
            self.process_start_stream(payload, addr)
        elif packet_type == 0xd2:
            self.process_mid_stream(payload, addr)
        elif packet_type == 0xd3:
            self.process_end_stream(payload, addr)
        elif packet_type == 0xd4:
            self.process_reduced_stream_data(payload, addr)
        elif packet_type == 0xc1:
            self.process_shock_data(payload, addr)
        else:
            self.process_unknown_data(payload, addr)



    def process_sync_data(self, payload, addr):
        """
        The `process_sync_data` function processes synchronization data, checks device status, sends
        configuration, checks files, logs peak frequencies, system monitoring data, and sends files to
        Influx and FTP server.
        
        :param payload: The `payload` parameter in the `process_sync_data` method likely contains data that
        needs to be processed during synchronization. It is used in various method calls within the
        function, such as `check_device(payload)`, `send_config(addr)`, and `check_files(addr, 0)`. The
        :param addr: The `addr` parameter in the `process_sync_data` method seems to represent the address
        of a device or a location to which data is being synchronized. It is used throughout the method for
        various purposes such as logging, updating device information, sending configuration, checking
        files, and sending data to specific addresses
        """

        # 1. LOG IMMEDIATO
        self.append_history('%d/%d/%d, %d:%d:%d, %s - Syncronization request\n' % (
            self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second, addr
        ))

        # 2.PRIORITA HARDWARE (sync e configurazione)
        device_status = self.check_device(payload)
        config_status = self.send_config(addr)

        # Inizializzazione dati per log unico
        if addr not in self.device_dict:
            self.update_device_file(addr)
        if addr not in self.file2s_fastapi_dict:
            self.file2s_fastapi_dict[addr] = []

        # 3. ANALISI DATI (fft e sys monitor)
        current_fft = self.fft_dict.get(addr, {})                             #se non c'e' FFT per questo addr, uso dict di default
        peaks_list = []
        i = 1
        # Continua a cercare finché trova peak_freq_1, peak_freq_2, ecc.
        while f'peak_freq_{i}' in current_fft:
            freq = current_fft[f'peak_freq_{i}']
            mag = current_fft[f'max_mag_{i}']
            peaks_list.append(f"f{i}: {freq:.4f}Hz (mag: {mag:.4f})")
            i += 1

        if peaks_list:
            fft_dict = "Peaks: " + " | ".join(peaks_list) + "\n"
        else:
            fft_dict = "Peaks: None or FFT not run\n"

        process_time_cpu = current_fft.get('process_time', -1)
        wall_time_cpu = current_fft.get('wall_time', -1)
        percentage_cpu = current_fft.get('percentage_cpu', -1)
        peak_memrss = current_fft.get('memrss', -1)

        sys_monitor = f"Process time: {process_time_cpu:.2f}, Wall time: {wall_time_cpu:.2f}, %CPU: {percentage_cpu:.2f}, RAM: {peak_memrss:.2f}"

        # checkF_status = self.check_files(addr, 0)
        # if checkF_status != '':
        #     self.append_history("\t" + checkF_status + "\n")

        # 4. GESTIONE UPLOAD
        try:
            # FastAPI
            self.fastapi_handler.upload_file(
                addr=addr,
                files_to_send=self.file2s_fastapi_dict.get(addr, []),
                local_dir=self.DATA_DIR,
                fft_result=self.fft_dict.get(addr, {}),
                logger_callback=self.append_history
            )
        except Exception as e:
            self.append_history(f"\t[CRITICAL][FastAPI] Errore: {str(e)}\n")
        
        try:
            # invio al server ftp pulisce fisicamente file dal disco
            server_status = self.send_file_to_server(addr)
        except Exception as e:
            server_status = f"Errore critico FTP: {str(e)}"
            self.append_history(f"\t[CRITICAL][FTP] Errore: {str(e)}\n")

        full_log_entry = f"\t{device_status.strip()}\n\t{fft_dict}\t{sys_monitor}\t{config_status.strip()}\n"
        # Scrittura nel log
        if server_status:
            full_log_entry += f"\t[FTP] {server_status}"
        
        self.append_history(full_log_entry)

        # cleanup finale
        self.fft_dict.pop(addr, None)



    def process_start_stream(self, payload, addr):
        """
             Processa il contenuto del pacchetto 0xD1 (inizio stream di dati).
             1 - Verifica che non ci siano altri file ancora aperti per quel sensore;
             2 - Inizializza un nuovo file con i parametri ricevuti nel payload;
             3 - Traduce i primi dati accelerometrici contenuti nel payload e li scrive nel file.
        """
        self.append_history(f'{self.t.strftime("%d/%m/%Y, %H:%M:%S")}, {addr} - Start data transmission\n')
        checkF_status = self.check_files(addr, 1)
        if checkF_status != '':
            self.append_history("\t" + checkF_status + "\n")

        # 0. Parsing tramite Decoder
        header = ProtocolDecoder.parse_start_header(payload)

        # Mapping delle baseline
        axis_idx_map = {'Xaxis': 0, 'Yaxis': 1, 'Zaxis': 2}
        idx = axis_idx_map.get(header['axis_label'], 0)
        self.first_data_dict[addr] = header['baselines'][idx]

        # 1. Preparazione stringhe per compatibilita load_sensor
        acc_range = header['range'] + ";"
        acc_odr = header['odr'] + ";"
        acc_axis = header['axis_file'] + ";\n"
        sync = header["sync"] + ";\n"

        # 2. Decoding dei valori medi (decode_samples passandogli gli 8 byte delle medie)
        mean_val = ProtocolDecoder.decode_samples(payload[23:31], 0)

        # 3. Creazioen file
        date_time = self.t.strftime('%d_%m_%Y_%H_%M_%S')
        filename = f"{self.DATA_DIR}{addr}_{header['axis_label']}_{date_time}.log"
        self.open_file_dict[addr] = filename
        self.pack_num_dict[addr] = 1

        with open(filename, 'w+') as f:
            # ricostruzione header
            f.write(f"{header['time']};{acc_range}{acc_odr}{acc_axis}{sync}")
            f.write(f"{';'.join(mean_val)};\n")
            f.write(f"{header['baselines'][0]};{header['baselines'][1]};{header['baselines'][2]};\n")
        
        # 4. Processamento effettivo dei campioni dati
        acq_data = self._process_stream_data(payload[31:], addr, first_value=0, is_append=True)




    def process_mid_stream(self, payload, addr):
        date_time = '%d_%d_%d_%d_%d_%d' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second)
        n_pck = ProtocolDecoder.get_packet_number(payload)
        checkF_status = self.check_files(addr, n_pck)                   #validazione packet stream
        
        if checkF_status != '':                                 #check se pkg e' ok
            self.append_history("\t" + checkF_status + "\n")
            if "Anomalous closure" in checkF_status:
                filename =  self.DATA_DIR + addr + '_UnknownAxis_' + date_time + '.log'
                self.file2s_dict_ftp[addr] = [filename]
                with open(filename, 'w+') as f:
                    f.write('* MISSING PACKETS FROM 1 TO %d *;' % (n_pck - 1))

        first_val = self.first_data_dict.get(addr, 0)           #valore baseline
        acq_data = self._process_stream_data(payload[3:], addr, first_val, is_append=True)



    def process_end_stream(self, payload, addr):
        """
            Gestisce la chiusura della sessione di una trasmissione dati
        """

        self.append_history('%d/%d/%d, %d:%d:%d, %s - End data transmission\n' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second, addr))

        date_time = '%d_%d_%d_%d_%d_%d' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second)

        n_pck = ProtocolDecoder.get_packet_number(payload)
        checkF_status = self.check_files(addr, n_pck)
        if checkF_status != '':
            self.append_history("\t" + checkF_status + "\n")
            if "Anomalous closure" in checkF_status:
                filename =  self.DATA_DIR + addr + '_UnknownAxis_' + date_time + '.log'
                self.file2s_dict_ftp[addr] = [filename]
                with open(filename, 'w+') as f:
                    f.write('* MISSING PACKETS FROM 1 TO %d *;' % (n_pck - 1))
        first_val = self.first_data_dict.get(addr, 0)
        acq_data = self._process_stream_data(payload[3:], addr, first_val, is_append=True)

        if addr in self.open_file_dict and self.open_file_dict[addr]:
            full_path = self.open_file_dict[addr]
            file2send = full_path.replace( self.DATA_DIR, '') 

            # aggiunge file valido alla coda
            if addr in self.file2s_dict_ftp:
                self.file2s_dict_ftp[addr].append(file2send)
            else:
                self.file2s_dict_ftp[addr] = [file2send]

            self.work_flow_fft(addr, full_path)         # start pipeline FFT

            # aggiunta alla coda influxdb e fastapi
            if checkF_status == '':
                self.file2s_fastapi_dict.setdefault(addr, []).append(file2send)

        else:
            self.append_history(f"\t[WARN] Nessun file aperto per {addr}\n")

        # Cleanup dizionari
        if addr in self.open_file_dict:
            self.open_file_dict.pop(addr)
        if addr in self.first_data_dict:
            self.first_data_dict.pop(addr)
        self.pack_num_dict[addr] = 0            #reset pkg counter



    def process_reduced_stream_data(self, payload, addr):
        self.append_history(f'{self.t.strftime("%d/%m/%Y, %H:%M:%S")}, {addr} - Shock data transmission\n')

        date_time = self.t.strftime("%d_%m_%Y_%H_%M_%S")

        # creazione file
        filename =  f"{self.DATA_DIR}{addr}_{date_time}_reduced.log"

        # 0. Parsing header
        header = ProtocolDecoder.parse_reduced_header(payload)

        # 1. Scrittura header
        with open(filename, 'w+') as f:
            f.write(f"{header['time']};{header['range']};{header['odr']};{header['axis_file']};\n")
            f.writelines(f"{header['sync']};\n")
        
        # 2. Scrittura dati
        self._process_stream_data(payload[11:], addr, first_value=0, is_append=True)

        # 3. Cleanup: rimuovo dalla gestione stream il file (autoconclusivo)
        self.open_file_dict.pop(addr, None)
        self.file2s_dict_ftp.setdefault(addr, []).append(filename.replace(self.DATA_DIR, ''))       #inserisce nella coda FTP



    def process_shock_data(self, payload, addr):
        """
            Gestisce l'evento di shock: header solo con timestamp => samples.
            Invio immediato a FTP
        """
        self.append_history(f"{self.t.strftime('%d/%m/%Y, %H:%M:%S')}, {addr} - Shock data transmission\n")
        
        # 0 Parsing header
        header = ProtocolDecoder.parse_shock_header(payload)

        date_time = self.t.strftime('%d_%m_%Y_%H_%M_%S')

        filename =  f"{self.DATA_DIR}{addr}_{date_time}_shock.log"
        
        self.open_file_dict[addr] = filename
        # 1. Scrittura header
        with open(filename, 'w+') as f:
            f.write(header["time"] + ';')

        # 2. Decoding e scrittura su file
        self._process_stream_data(payload[4:], addr, first_value=0, is_append=True)

        # 3. Invio immediato al server per dati di shock
        server_status = self.send_file_to_server(addr)
        self.append_history("\t" + server_status + "\n")

        # 2. Scrittura su file
        # with open(filename, 'w+') as f:
        #     f.write(header["time"] + ';')
        #     shock_data = ProtocolDecoder.decode_samples(payload[4:], 0)
        #     for c in shock_data:
        #         f.write(c + ';')

        # file2send = filename.replace( self.DATA_DIR, '')
        # if file2send:  
        #     if addr in self.file2s_dict_ftp:
        #         self.file2s_dict_ftp[addr].append(file2send)
        #     else:
        #         self.file2s_dict_ftp[addr] = [file2send]

    
    def process_unknown_data(self, payload, addr):
        """
            Gestisce pacchetto non identificato: 
                aggiungo evento all'history e skippo
        """
        self.append_history('%d/%d/%d, %d:%d:%d, %s - Unexpected data transmission\n' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second, addr))
        self.append_history("\t" + self.original_payload.hex() + "\n") #cambiato da encode a hex



    def update_device_file(self, addr):
        """
            Aggiorna il delay di invio d el sensore.
            (delay incrementale non so perche)
        """
        self.device_dict[addr] = self.delay
        self.delay = self.delay + self.delay_time   
        with open(self.device_file, 'a') as f:
            f.write(addr + ' %02d \n' % self.device_dict[addr])



    def check_device(self, p):

        # Decoding del payload
        info = ProtocolDecoder.parse_sync_info(p)

        # Costruzione del messaggio di status
        status = f"Datetime: {info['datetime']}\n"

        if info['battery'] is not None:
            status += f"\tBattery: {info['battery']:.3f} V\n\tRSSI: {info['rssi']} dB\n"
        if info['temp'] is not None:
            status += f"\tTemperature: {info['temp']:.2f} C\n\tHumidity: {info['humidity']:.2f}\n"
        if info['reset_bit'] is not None:
            status += f"\tReset bit: {info['reset_bit']}\n"
        
        gps_map = {0: 'no signal', 1: 'connected, pps ok'}
        status += f"\tGPS: {gps_map.get(info['gps_status'], 'connected no pps')}\n"

        hw_errors = [
            (info['errors']['362'], "ADXL362"),
            (info['errors']['355'], "ADXL355"),
            (info['errors']['mem'], "Memory")
        ]
        for err_code, name in hw_errors:
            if err_code == 1: status += f"\t{name}: Error\n"
            elif err_code != 0: status += f"\t{name} bit error: {err_code:x}\n"
        
        if info['errors']['radio'] != 0:
            status += f"\tRadio error code: {info['errors']['radio']}\n"

        cfg = info['errors']['config']
        if cfg & 0x01: status += "\tConfig bits on range high\n"
        if cfg & 0x02: status += "\tConfig bits on ODR high\n"
        if cfg & 0x04: status += "\tConfig bits on axis all set to zero\n"
        if cfg & 0x08: status += "\tConfig bits on samples high\n"

        return status


    
    def work_flow_fft(self, addr, log_file_path):

        try:
            start_cpu = time.process_time()                                 #snapshot iniziale CPU e tempo reale
            start_wall = time.perf_counter()
            # 1. caricamento dati
            data_loaded = load_sensor(log_file_path)
            samples = data_loaded["samples"]
            fs = data_loaded["metadata"]["fs"]
            
            if(len(samples) > 0):
                res_fft = start_fft(samples, fs)                            # risultati fft
            else:
                print(f"\t[WARNING] Nessun campione nel file per FFT")

            if self.is_flexibile_structure:
                peaks = get_top_peaks_prominence(res_fft, fs)
            elif not self.is_flexibile_structure:
                peaks = get_top_peaks_resolution(res_fft, fs)
            
            # init del dizionario per id di sensore
            self.fft_dict[addr] ={
                'peak_freq': -1, 'max_mag': -1,
                'process_time': -1, 'wall_time': -1,
                'percentage_cpu': -1, 'memrss': -1
            }

            if peaks:
                self.fft_dict[addr]['peak_freq'] = peaks[0]['freq']
                self.fft_dict[addr]['max_mag'] = peaks[0]['mag']
                for i,p in enumerate(peaks):
                    self.fft_dict[addr][f'peak_freq_{i+1}'] = p['freq']
                    self.fft_dict[addr][f'max_mag_{i+1}'] = p['mag']
            else:
                print(f"\t[WARNING] nessun campione nel file per FFT per sensore {addr}")
            
            end_cpu = time.process_time()
            end_wall = time.perf_counter()                                  # snapshot finale
            
            cpu_delta = end_cpu - start_cpu
            wall_delta = end_wall - start_wall                              # calcolo differenze
            
            cpu_percent = (cpu_delta / wall_delta) * 100 if (wall_delta > 0) else 0             # calcolo % cpu
            
            mem_peal = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            
            self.fft_dict[addr]["process_time"] = cpu_delta
            self.fft_dict[addr]["wall_time"] = wall_delta
            self.fft_dict[addr]["percentage_cpu"] = cpu_percent
            self.fft_dict[addr]["memrss"] = mem_peal

        except Exception as e:
            print(f"\t[ERROR] Errore durante FFT: {str(e)}\n")



    def send_config(self, addr):
        """
        Costruisce e trasmette il pacchetto di sincronizzazione(0xA1 o 0xA2) al sensore che ne ha fatto richiesta.
        I dati cambiano in base alla presenza o meno dell'identificativo del sensore all'interno del file "config.txt".
        """
        delay = self.device_dict.get(addr, 0)
        
        if addr in self.config_dict:
            # Se gia presente => genera pacchetto riconfig (0xA2)
            config_hex = ProtocolDecoder.build_config_packet(self.config_dict[addr], delay)
            status = 'Sent reconfiguration\n'
        else:
            # Invio semplicemnete pacchettodi sync 
            # Altrimenti => genera pacchetto Sync (0xA1)
            config_hex = ProtocolDecoder.build_sync_packet(delay)
            status = 'Sync sent\n'
        
        # mandManda la configurazione al sensore
        self.xbee.send_data(addr, config_hex, self.append_history)
        return status

   

    def check_files(self, addr, n_pack):
        """
            Controlla se lo stream dei pacchetti per sta seguendo il giusto ordine
            e se ci sono file che non sono stati chiusi per il sensore.

            Return: status='' (empty) se tutto ok / status = str (str=err) altrimenti
            Param: 
                - addr: MAC sensore
                - n_pack: numero di package estratto dal payload
            
            Info: pack_num_dict: dict che mappa 'addr -> last n_pack'
        """
        status = ''
        if addr in self.open_file_dict:
            if n_pack < self.pack_num_dict[addr] + 1:       # se il numero di paccheto non combacia
                with open(self.open_file_dict[addr], 'a') as f:
                    status = '\tAnomalous closure for data stream - %s\n' % self.open_file_dict[addr]
                    f.write('* INCOMPLETE TRANSMISSION *;')
                file2send = self.open_file_dict[addr].replace( self.DATA_DIR, '')
                if addr in self.file2s_dict_ftp:
                    self.file2s_dict_ftp[addr].append(file2send)
                else:
                    self.file2s_dict_ftp[addr] = [file2send]
                self.open_file_dict.pop(addr)
                if addr in self.first_data_dict: self.first_data_dict.pop(addr)
            elif n_pack > self.pack_num_dict[addr] + 1:
                with open(self.open_file_dict[addr], 'a') as f:
                    status = '\tMissing packets from %d to %d - %s\n' % (self.pack_num_dict[addr] + 1, n_pack - 1, addr)
                    f.write('* MISSING PACKETS FROM %d TO %d *;' % (self.pack_num_dict[addr] + 1, n_pack - 1))
        elif n_pack > 1:
            status = '\tAnomalous closure - missing data from device: %s\n' % addr
            if addr in self.first_data_dict: self.first_data_dict.pop(addr)
        self.pack_num_dict[addr] = n_pack
        return status



    def send_file_to_server(self, addr):
        """
        Trasmette i dati al server tramite FTP. (tutti quelli a disposizione per il sensore)
        Se l'upload ha successo, cancella i file locali.
        """
        if addr in self.file2s_dict_ftp and self.file2s_dict_ftp[addr]:
            result = self.ftp_handler.upload_files(
                addr=addr,
                files_to_send=self.file2s_dict_ftp[addr],
                logger_callback=self.append_history
            )
            
            # se upload riuscito svuota la coda (pulizia file in ftp_manager)
            if "OK" in result or "success" in result.lower():
                self.file2s_dict_ftp[addr] = []  # Svuota la coda
            
            return result
        return ""



    def _cleanup_files(self, addr, files_list):
        """
        Cancella i file dalla memoria locale dopo un invio riuscito.
        
        Args:
            addr (str): Indirizzo dispositivo
            files_list (list): Lista di nomi file da cancellare
        """
        base_path =  self.DATA_DIR
        for filename in files_list:
            full_path = base_path + filename
            try:
                if os.path.exists(full_path):
                    os.remove(full_path)
                    self.append_history(f"\t[CLEANUP] File rimosso: {filename}\n")
            except Exception as e:
                self.append_history(f"\t[ERROR] Impossibile rimuovere {filename}: {str(e)}\n")

    """
        Gestore della coda: processa tutti i file in attesa per sensore
            - verifica se in file2s_influx_dict ci sono file per l'invio
            - per ogni file che trova chiama la worker create_influx_line_protocol
            - log e pulizia
    """
    # def send_file_to_influx(self, addr):

    #     """
    #     Trasmette i dati a InfluxDB.
    #     Se l'upload ha successo, cancella i file locali.
    #     """
        
    #     current_fft_res = self.fft_dict.get(addr, {})

    #     if addr in self.file2s_influx_dict and self.file2s_influx_dict[addr]:
    #         try:
    #             self.influx_handler.upload_influx_data(
    #                 addr=addr,
    #                 files_to_send=self.file2s_influx_dict[addr],
    #                 fft_result=current_fft_res,
    #                 logger_callback=self.append_history
    #             )
                
    #             # Se upload riuscito (pulizia file in ftp_manager)
    #             self.file2s_influx_dict[addr] = []  # Svuota la coda
                
    #         except Exception as e:
    #             self.append_history(f"\t[ERROR] Errore Influx per {addr}: {str(e)}\n")




    def append_history(self, stringa):
        """
            Scrive una riga nel file di history
        """
        with open(self.logger_file, 'a') as f:
            f.write(stringa)

    # SPOSTATO IN PROTOCO_DECODER
    # def decode_payload(self, cut_payload, first):


    def main(self):
        try:
            self.t = datetime.now()

            payload, address, raw_bytes = self.xbee.receive_data(self.append_history)

            if payload is None or address is None:
                return
            self.original_payload = raw_bytes           # salviamo i byte originali per process_unknown_data

            self.check_device_config()
            self.process_data(payload, address)
        except Exception as e:
            self.append_history("\tErrore generale nel main: %s\n" % str(e))



if __name__ == "__main__":
    gw = Gateway()
    gw.run()
