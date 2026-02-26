# The `Gateway` class is a Python program that handles data received from sensors, processes the data,
# performs FFT analysis, sends data to InfluxDB and FTP server, and logs the process in a history
# file.
# coding=utf-8
import os
import cmath
import ctypes
import resource
from digidevice import xbee
from datetime import datetime, timezone
import time
import json
import serial
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

"""
============================================
"""

class Gateway:
    # Inizializzazione della classe Gateway().
    def __init__(self):
        
        self.device_dict = dict()
        self.config_dict = dict()
        self.file2s_dict = dict()
        self.file2s_influx_dict = dict()
        
        self.open_file_dict = dict()
        self.pack_num_dict = dict()
        self.first_data_dict = dict()
        
        # Carico config FTP, influx e gw dal config
        self.load_gateway_config()

        # ISTANZIO GESTORE FTP
        self.ftp_handler = FTPClient(
            server=self.server_name,
            user=self.username,
            pwd=self.pwd,
            path=self.server_path,
            local_dir='/etc/config/scripts/SHM_Data/'
        )
        
        self.original_payload = ''
        self.delay = 0
        self.delay_time = 0
        self.t = datetime.now()
        self.address = ''
        self.device = self.get_device()

        self.fft_dict = dict(peak_freq = -1, max_mag = -1, process_time = -1, wall_time = -1, percentage_cpu = -1, memrss = -1)
        
        self.device.open() # Apertura della connessione 

        # cancella il file che gestisce i sensori
        f = open(self.device_file, 'w+')
        f.close()

        while True: 
            self.main()

    def load_gateway_config(self):
        config_path = "/etc/config/scripts/gw_config.json"   
        
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
                self.influx_url = config['influxdb']['url']
                self.influx_token = config['influxdb']['token']
                
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
            
            
    def get_device(self):
        device = xbee.get_device()
        return device

    # Aspetta di ricevere un pacchetto dati sul canale impostato nel gateway, da qualunque fonte.
    # I valori restituiti sono il payload e l'indirizzo del dispositivo che ha trasmesso i dati.
    def get_data(self):
        """
        The function `get_data` reads data from a device, extracts the payload and address, and handles
        exceptions by logging errors.
        :return: The `get_data` method returns a tuple containing `list_pl` and `addr`. If an exception
        is caught during the execution of the method, it will return `None, None`. If the exception
        message contains the word "timeout", it will also return `None, None` without logging the error.
        """
        try:
            xbee_message = self.device.read_data(timeout=5)
            if xbee_message is None:
                return None, None
            self.remote_device = xbee_message.remote_device
            if hasattr(xbee_message.remote_device, 'get_64bit_addr'):
                addr = str(xbee_message.remote_device.get_64bit_addr()).lower()
            else:
                addr = str(xbee_message.remote_device).lower()
            pl = xbee_message.data
            list_pl = list(pl)
            self.t = datetime.now()
            self.original_payload = pl
            return list_pl, addr
        except Exception as e:
            # Se il messaggio di errore contiene "timeout", ignora e non loggare
            if "timeout" in str(e).lower():
                return None, None
            # Altri errori vengono loggati
            self.append_history("\tErrore in get_data: %s\n" % str(e))
            return None, None
    
    # Aggiorna il dizionario che contiene le configurazioni dei sensori.
    # Ogni riga corrisponde ad un sensore diverso
    def check_device_config(self):
        """
        The function `check_device_config` reads a configuration file line by line, extracts sensor names
        and parameters, and stores them in a dictionary.
        """
        with open(self.config_file, 'r') as c:
            lines = c.readlines()               # Legge tutte le righe insieme.
            for line in lines:                  # Analizza una riga per volta.
                config_address = line[:16]      # Nome sensore.
                config_parameters = line[17:]   # Parametri.
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

    # Processa il contenuto del pacchetto 0xA1 (sincronizzazione).
    # 1 - Verifica che il sensore sia mappato nel file "devices.txt", e nel caso, lo aggiunge alla lista;
    # 2 - Verifica lo stato del sensore;
    # 3 - Risponde alla richiesta di sincronizzazione;
    # 4 - Verifica che non ci siano altri file ancora aperti per quel sensore;
    # 5 - Sposta i file del dispositivo corrispondente nel server;
    # 6 - Riporta i risultati nel file "history.log".
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
        self.append_history('%d/%d/%d, %d:%d:%d, %s - Syncronization request\n' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second, addr))
        if addr not in self.device_dict: 
            self.update_device_file(addr)

        device_status = self.check_device(payload)
        config_status = self.send_config(addr)
        checkF_status = self.check_files(addr, 0)

        # --- NUOVA LOGICA PER LOG PICCHI MULTIPLI ---
        peaks_list = []
        i = 1
        # Continua a cercare finché trova peak_freq_1, peak_freq_2, ecc.
        while f'peak_freq_{i}' in self.fft_dict:
            freq = self.fft_dict[f'peak_freq_{i}']
            mag = self.fft_dict[f'max_mag_{i}']
            peaks_list.append(f"f{i}: {freq:.4f}Hz (mag: {mag:.4f})")
            i += 1

        if peaks_list:
            fft_result = "Peaks: " + " | ".join(peaks_list) + "\n"
        else:
            fft_result = "Peaks: None or FFT not run\n"
        # --------------------------------------------

        process_time_cpu = self.fft_dict.get('process_time', -1)
        wall_time_cpu = self.fft_dict.get('wall_time', -1)
        percentage_cpu = self.fft_dict.get('percentage_cpu', -1)
        peak_memrss = self.fft_dict.get('memrss', -1)

        sys_monitor = f"Process time: {process_time_cpu:.2f}, Wall time: {wall_time_cpu:.2f}, %CPU: {percentage_cpu:.2f}, RAM: {peak_memrss:.2f}"

        if checkF_status != '':
            self.append_history("\t" + checkF_status + "\n")

        # manda i file accumulati a influx
        self.send_file_to_influx(addr)
        
        # invio al server ftp
        server_status = self.send_file_to_server(addr)

        # Scrittura nel log
        self.append_history("\t" + device_status + "\t" + fft_result + "\t" + sys_monitor + "\t" + config_status + "\n")
        if server_status != '':
            self.append_history("\t" + server_status + "\n")

    
    # Processa il contenuto del pacchetto 0xD1 (inizio stream di dati).
    # 1 - Verifica che non ci siano altri file ancora aperti per quel sensore;
    # 2 - Inizializza un nuovo file con i parametri ricevuti nel payload;
    # 3 - Traduce i primi dati accelerometrici contenuti nel payload e li scrive nel file.
    def process_start_stream(self, payload, addr):
        self.append_history('%d/%d/%d, %d:%d:%d, %s - Start data transmission\n' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second, addr))
        date_time = '%d_%d_%d_%d_%d_%d' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second)
        checkF_status = self.check_files(addr, 1)
        if checkF_status != '':
            self.append_history("\t" + checkF_status + "\n")

        recv_time = '{:x}'.format(payload[3]) + ':' + '{:x}'.format(payload[4]) + ':' + '{:x}'.format(payload[5])

        first_data_x = ctypes.c_int32(ctypes.c_uint32(payload[11] << 24 | payload[12] << 16 | payload[13] << 8 | payload[14]).value).value / 10000000.0
        first_data_y = ctypes.c_int32(ctypes.c_uint32(payload[15] << 24 | payload[16] << 16 | payload[17] << 8 | payload[18]).value).value / 10000000.0
        first_data_z = ctypes.c_int32(ctypes.c_uint32(payload[19] << 24 | payload[20] << 16 | payload[21] << 8 | payload[22]).value).value / 10000000.0

        if payload[6] == 0x01: acc_range = '2g;'
        elif payload[6] == 0x02: acc_range = '4g;'
        elif payload[6] == 0x03: acc_range = '8g;'
        else: acc_range = 'bad range value;'

        if payload[7] == 0x07: acc_odr = '31.25 Hz;'
        elif payload[7] == 0x06: acc_odr = '62.5 Hz;'
        elif payload[7] == 0x05: acc_odr = '125 Hz;'
        elif payload[7] == 0x04: acc_odr = '250 Hz;'
        elif payload[7] == 0x03: acc_odr = '500 Hz;'
        else: acc_odr = 'bad ODR value;'

        if payload[8] == 0x01: 
            axis = 'Xaxis'
            acc_axis = 'X axis;\n'
            self.first_data_dict[addr] = first_data_x
        elif payload[8] == 0x02: 
            axis = 'Yaxis'
            acc_axis = 'Y axis;\n'
            self.first_data_dict[addr] = first_data_y
        elif payload[8] == 0x03: 
            axis = 'Zaxis'
            acc_axis = 'Z axis;\n'
            self.first_data_dict[addr] = first_data_z
        else: 
            axis = 'UnknownAxis'
            acc_axis = 'bad axis value;\n'
            self.first_data_dict[addr] = 0

        if payload[9] == 0: sync = 'Asynced;\n'
        elif payload[9] == 1: sync = 'Synced;\n'
        elif payload[9] == 2: sync = 'Synced2;\n'
        else: sync = 'Unknown;\n'

        mean_val = self.decode_payload(payload[23:31], 0)
        acq_data = self.decode_payload(payload[31:], self.first_data_dict[addr])

        filename = '/etc/config/scripts/SHM_Data/' + addr + '_' + axis + '_' + date_time + '.log'
        self.open_file_dict[addr] = filename
        with open(self.open_file_dict[addr], 'w+') as f:
            f.write(recv_time + ";" + acc_range + acc_odr + acc_axis + sync + mean_val[0] + ";" + mean_val[1] + ";" + mean_val[2] + ";" + mean_val[3] + ";\n" + str(first_data_x) + ";" + str(first_data_y) + ";" + str(first_data_z) + ";\n")      
            for d in acq_data:
                f.write(d + ';')

    # Processa il contenuto del pacchetto 0xD2 (continuazione stream di dati).
    # 1 - Verifica che il numero del pacchetto sia quello aspettato, nel caso apre un nuovo file;
    # 2 - Traduce i dati e li scrive nel file.
    def process_mid_stream(self, payload, addr):
        date_time = '%d_%d_%d_%d_%d_%d' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second)
        n_pck = (payload[1] << 8) | payload[2]
        checkF_status = self.check_files(addr, n_pck)
        if checkF_status != '':
            self.append_history("\t" + checkF_status + "\n")
            if "Anomalous closure" in checkF_status:
                filename = '/etc/config/scripts/SHM_Data/' + addr + '_UnknownAxis_' + date_time + '.log'
                self.file2s_dict[addr] = [filename]
                with open(filename, 'w+') as f:
                    f.write('* MISSING PACKETS FROM 1 TO %d *;' % (n_pck - 1))

        if addr in self.first_data_dict:
            acq_data = self.decode_payload(payload[3:], self.first_data_dict[addr])
        else:
            acq_data = self.decode_payload(payload[3:], 0)

        # PATCH: controlla che il file sia ancora aperto/valido prima di scrivere
        if addr in self.open_file_dict and os.path.exists(self.open_file_dict[addr]):
            with open(self.open_file_dict[addr], 'a') as f:
                for d in acq_data:
                    f.write(d + ';')
        else:
            self.append_history(f"\t[WARN] Tentativo di scrivere su file chiuso o inesistente per {addr}\n")

    # Processa il contenuto del pacchetto 0xD3 (fine stream di dati).
    # 1 - Verifica che il numero del pacchetto sia quello aspettato, nel caso apre un nuovo file;
    # 2 - Traduce i dati e li scrive nel file;
    # 3 - Prepara il file per la trasmissione al server;
    # 4 - Resetta il numero di pacchetto aspettato a 0 per la prossima trasmissione.
    def process_end_stream(self, payload, addr):
        """
        This Python function processes end data transmission, checks for anomalies, decodes payload,
        writes data to files, performs FFT, and adds data to an InfluxDB queue.
        
        :param payload: The `payload` parameter in the `process_end_stream` method seems to be a byte
        array or a list of bytes. It is used to extract information such as packet number and
        acquisition data from the incoming data stream. The method processes the end of a data
        transmission stream and performs various operations based on
        :param addr: The `addr` parameter in the `process_end_stream` method seems to represent an
        address or identifier associated with the data transmission process. It is used for various
        purposes within the method, such as constructing file paths, checking file status, decoding
        payload data, and managing dictionaries related to file handling and data
        """
        self.append_history('%d/%d/%d, %d:%d:%d, %s - End data transmission\n' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second, addr))
        date_time = '%d_%d_%d_%d_%d_%d' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second)
        n_pck = (payload[1] << 8) | payload[2]
        checkF_status = self.check_files(addr, n_pck)
        if checkF_status != '':
            self.append_history("\t" + checkF_status + "\n")
            if "Anomalous closure" in checkF_status:
                filename = '/etc/config/scripts/SHM_Data/' + addr + '_UnknownAxis_' + date_time + '.log'
                self.file2s_dict[addr] = [filename]
                with open(filename, 'w+') as f:
                    f.write('* MISSING PACKETS FROM 1 TO %d *;' % (n_pck - 1))
    
        if addr in self.first_data_dict:
            acq_data = self.decode_payload(payload[3:], self.first_data_dict[addr])
        else:
            acq_data = self.decode_payload(payload[3:], 0)

        # PATCH: controlla che il file sia ancora aperto/valido prima di scrivere
        if addr in self.open_file_dict and os.path.exists(self.open_file_dict[addr]):
            with open(self.open_file_dict[addr], 'a') as f:
                for d in acq_data:
                    f.write(d + ';')
        else:
            self.append_history(f"\t[WARN] Tentativo di scrivere su file chiuso o inesistente per {addr}\n")
        
        
        """
        ==================================
        """
        
        full_path = self.open_file_dict[addr]
        file2send = self.open_file_dict[addr].replace('/etc/config/scripts/SHM_Data/', '') if addr in self.open_file_dict else None
        if file2send and full_path:
            if addr in self.file2s_dict:
                self.file2s_dict[addr].append(file2send)
            else:
                self.file2s_dict[addr] = [file2send]
            # chiamata fft
            res_fft = self.work_flow_fft(full_path)
            
            # aggiunta alla coda influxdb
            if checkF_status == '':
                if addr in self.file2s_influx_dict:
                    self.file2s_influx_dict[addr].append(file2send)
                else:
                    self.file2s_influx_dict[addr] = [file2send]
            
        if addr in self.open_file_dict:
            self.open_file_dict.pop(addr)
        if addr in self.first_data_dict:
            self.first_data_dict.pop(addr)
        self.pack_num_dict[addr] = 0


    # Processa il contenuto del pacchetto 0xD4 (dati ridotti).
    # 1 - Traduce i dati e li scrive in un nuovo file.
    def process_reduced_stream_data(self, payload, addr):
        self.append_history('%d/%d/%d, %d:%d:%d, %s - Reduced data transmission\n' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second, addr))

        date_time = '%d_%d_%d_%d_%d_%d' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second)
        filename = '/etc/config/scripts/SHM_Data/' + addr + '_' + date_time + '_reduced.log'

        recv_time = '{:x}'.format(payload[3]) + ':' + '{:x}'.format(payload[4]) + ':' + '{:x}'.format(payload[5])

        if payload[6] == 0x01: acc_range = '2g;'
        elif payload[6] == 0x02: acc_range = '4g;'
        elif payload[6] == 0x03: acc_range = '8g;'
        else: acc_range = 'bad range value;'

        if payload[7] == 0x07: acc_odr = '31.25 Hz;'
        elif payload[7] == 0x06: acc_odr = '62.5 Hz;'
        elif payload[7] == 0x05: acc_odr = '125 Hz;'
        elif payload[7] == 0x04: acc_odr = '250 Hz;'
        elif payload[7] == 0x03: acc_odr = '500Hz;'
        else: acc_odr = 'bad ODR value;'

        if payload[8] == 0x01: acc_axis = 'X axis;\n'
        elif payload[8] == 0x02: acc_axis = 'Y axis;\n'
        elif payload[8] == 0x03: acc_axis = 'Z axis;\n'
        else: acc_axis = 'bad axis value;\n'

        if payload[9] == 0: sync = 'Asynced;\n'
        elif payload[9] == 1: sync = 'Synced;\n'
        elif payload[9] == 2: sync = 'Synced2;\n'
        else: sync = 'Unknown;\n'

        with open(filename, 'w+') as f:  
            f.write(recv_time + ";" + acc_range + acc_odr + acc_axis + sync + ";\n")      
            acq_data = self.decode_payload(payload[11:], 0)
            for c in acq_data:
                f.write(c + ';')

        file2send = filename.replace('/etc/config/scripts/SHM_Data/', '')
        if file2send:  # <-- controllo aggiunto
            if addr in self.file2s_dict:
                self.file2s_dict[addr].append(file2send)
            else:
                self.file2s_dict[addr] = [file2send]

    # Processa il contenuto del pacchetto 0xC1 (evento vibrazinale).
    # 1 - Traduce i dati e li scrive in un nuovo file.
    def process_shock_data(self, payload, addr):
        self.append_history('%d/%d/%d, %d:%d:%d, %s - Shock data transmission\n' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second, addr))
        
        date_time = '%d_%d_%d_%d_%d_%d' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second)
        filename = '/etc/config/scripts/SHM_Data/' + addr + '_' + date_time + '_shock.log'
        
        recv_time = '{:x}'.format(payload[1]) + ':' + '{:x}'.format(payload[2]) + ':' + '{:x}'.format(payload[3])
        shock_data = self.decode_payload(payload[4:], 0)
        
        with open(filename, 'w+') as f:
            f.write(recv_time + ';')
            for c in shock_data:
                f.write(c + ';')

        file2send = filename.replace('/etc/config/scripts/SHM_Data/', '')
        if file2send:  # <-- controllo aggiunto
            if addr in self.file2s_dict:
                self.file2s_dict[addr].append(file2send)
            else:
                self.file2s_dict[addr] = [file2send]

        server_status = self.send_file_to_server(addr)
        self.append_history("\t" + server_status + "\n")

    # Processa il contenuto del pacchetto.
    def process_unknown_data(self, payload, addr):
        self.append_history('%d/%d/%d, %d:%d:%d, %s - Unexpected data transmission\n' % (self.t.day, self.t.month, self.t.year, self.t.hour, self.t.minute, self.t.second, addr))
        self.append_history("\t" + self.original_payload.hex() + "\n") #cambiato da encode a hex

    # Aggiorna il file che mappa i sensori, impostando il delay del nuovo dispositivo.
    # Il delay specifica le tempistiche con le quali il dispositivo in questione dovra trasmettere.
    def update_device_file(self, addr):
        self.device_dict[addr] = self.delay
        self.delay = self.delay + self.delay_time
        with open(self.device_file, 'a') as f:
            f.write(addr + ' %02d \n' % self.device_dict[addr])

    # Verifica se ci sono dei problemi, tramite i parametri di sincronizzazzione ricevuti dal sensore.
    def check_device(self, p):
        data_recv = '{:x}'.format(p[1]) + '-' + '{:x}'.format(p[2]) + '-' + '{:x}'.format(p[3])
        time_recv = '{:x}'.format(p[4]) + ':' + '{:x}'.format(p[5]) + ':' + '{:x}'.format(p[6])
        status = 'Datetime: %s %s\n' % (data_recv, time_recv)

        if len(p) > 32:
            # Versione firmware 2 Wisesensing. (Batteria e RSSI)
            batt = (p[32] + (p[33] << 8)) * 0.001
            status = status + ('\tBattery: %s V\n\tRSSI: -%s dB\n' % (str(batt), str(p[34])))
            if len(p) > 35:
                # Versione firmware 3 Wisesensing. (Temperatura, umidita e bit di reset)
                temperature = (p[35] + (p[36] << 8)) * 0.01
                humidity = (p[37] + (p[38] << 8)) * 0.01
                status = status + ('\tTemperature: %s C\n\tHumidity: %s\n\tReset bit: %s\n' % (str(temperature), str(humidity), str(p[39] + (p[40] << 8))))

        if p[17] == 0: status = status + '\tGPS: no signal\n'
        elif p[17] == 1: status = status + '\tGPS: connected, pps ok\n'
        else: status = status + '\tGPS: connected no pps\n' #modificato, prima era 'no GPS'

        if p[7] == 1: status = status + "\tADXL362: Error\n"
        elif p[7] == 0: pass
        else: status = status + '\tADXL362 bit error: %x\n' % p[7]

        if p[8] == 1: status = status + "\tADXL355: Error\n"
        elif p[8] == 0: pass
        else: status = status + '\tADXL355 bit error: %x\n' % p[8]

        if p[9] == 1: status = status + "\tMemory: Error\n"
        elif p[9] == 0: pass
        else: status = status + '\tMemory bit error: %x\n' % p[9]

        if p[10] == 0: pass
        elif p[10] == 1: status = status + "\tRadio not inited during previous communication\n"
        elif p[10] == 2: status = status + "\tTx Error during previous communication\n"
        elif p[10] == 3: status = status + "\tModule not joined during previous communication\n"
        elif p[10] == 4: status = status + "\tBad start received\n"
        elif p[10] == 5: status = status + "\tBad sync received\n"
        elif p[10] == 6: status = status + "\tStart not received\n"
        elif p[10] == 7: status = status + "\tToo many data transferring errors during previous communication\n"
        elif p[10] == 8: status = status + "\tMissing API std response during previous communication\n"
        else: status = status + '\tRadio bit error: %x\n' % p[10]

        if p[11] & 0x01 == 1: status = status + "\tConfig bits on range high\n"
        if p[11] & 0x02 == 1: status = status + "\tConfig bits on ODR high\n"
        if p[11] & 0x04 == 1: status = status + "\tConfig bits on axis all set to zero\n"
        if p[11] & 0x08 == 1: status = status + "\tConfig bits on samples high\n"

        return status

    # Funzioen contenente la logica di lavoro della procedura fft:
    # 1. Carica i dati dal log del sensore tramite load_sensor
    # 2. Avvia la funzioene per il calcolo della fft:
    #   - IN => samples_sensore e fs
    #   - OUT => portante_principale, magnitudo_portante
    
    def work_flow_fft(self, log_file_path):
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
            
            if peaks:
                self.fft_dict['peak_freq'] = peaks[0]['freq']
                self.fft_dict['max_mag'] = peaks[0]['mag']

                for i,p in enumerate(peaks):
                    self.fft_dict[f'peak_freq_{i+1}'] = p['freq']
                    self.fft_dict[f'max_mag_{i+1}'] = p['mag']
            else:
                print(f"\t[WARNING] nessun capion nel file per FFT")
            
            end_cpu = time.process_time()
            end_wall = time.perf_counter()                                  # snapshot finale
            
            cpu_delta = end_cpu - start_cpu
            wall_delta = end_wall - start_wall                              # calcolo differenze
            
            cpu_percent = (cpu_delta / wall_delta) * 100 if (wall_delta > 0) else 0             # calcolo % cpu
            
            mem_peal = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            
            self.fft_dict["process_time"] = cpu_delta
            self.fft_dict["wall_time"] = wall_delta
            self.fft_dict["percentage_cpu"] = cpu_percent
            self.fft_dict["memrss"] = mem_peal
        except Exception as e:
            print(f"\t[ERROR] Errore durante FFT: {str(e)}\n")
            
            
                
    # Costruisce e trasmette il pacchetto di sincronizzazione al sensore che ne ha fatto richiesta.
    # I dati cambiano in base alla presenza o meno dell'identificativo del sensore all'interno del file "config.txt".
    def send_config(self, addr):
        status = 'Syncronization step not completed\n'
        t = datetime.now(timezone.utc)
        
        #timestamp_str = 'a1%02d%02d%02d%02d%02d%02d%04x%02x' % (int(str(t.year)[-2:]), t.month, t.day, 11, 55, 0, int(t.microsecond / 1000),self.device_dict[addr])
        timestamp_str = 'a1%02d%02d%02d%02d%02d%02d%04x%02x' % (int(str(t.year)[-2:]), t.month, t.day, t.hour, t.minute, t.second, int(t.microsecond / 1000), self.device_dict[addr])
        timestamp = bytes.fromhex(timestamp_str)
        
        if addr in self.config_dict:
            param = self.config_dict[addr].split(' ')

            if param[0] == '2g': acc = 0x01
            elif param[0] == '4g': acc = 0x02
            else: acc = 0x04

            if param[1] == '31_25Hz': odr = 0x08
            elif param[1] == '62_5Hz': odr = 0x10
            elif param[1] == '125Hz': odr = 0x20
            elif param[1] == '250Hz': odr = 0x40
            else: odr = 0x80

            if param[2] == 'X': ax = 0x100
            elif param[2] == 'Y': ax = 0x200
            elif param[2] == 'Z': ax = 0x400
            elif param[2] == 'XY': ax = 0x300
            elif param[2] == 'XZ': ax = 0x500
            elif param[2] == 'YZ': ax = 0x600
            else: ax = 0x700

            if param[3] == '2k': datakb = 0x800
            elif param[3] == '4k': datakb = 0x1000
            elif param[3] == '8k': datakb = 0x2000
            elif param[3] == '16k': datakb = 0x4000
            else: datakb = 0x8000

            if param[4] == '1h': sending_f = 0x0
            elif param[4] == '2h': sending_f = 0x01
            elif param[4] == '3h': sending_f = 0x02
            elif param[4] == '4h': sending_f = 0x03
            elif param[4] == '6h': sending_f = 0x04
            else: sending_f = 0x05

            if param[5] == 'SYNC1': sync_f = 0x00
            else: sync_f = 0x08

            if param[6] == '2g': range_sck = 0x01
            elif param[6] == '4g': range_sck = 0x02
            else: range_sck = 0x04

            if param[7] == '31_25Hz': acq_sck_odr = 0x08
            elif param[7] == '62_5Hz': acq_sck_odr = 0x10
            elif param[7] == '125Hz': acq_sck_odr = 0x20
            elif param[7] == '250Hz': acq_sck_odr = 0x40
            else: acq_sck_odr = 0x80

            if param[8] == 'X': sck_ax = 0x100
            elif param[8] == 'Y': sck_ax = 0x200
            elif param[8] == 'Z': sck_ax = 0x400
            elif param[8] == 'XY': sck_ax = 0x300
            elif param[8] == 'XZ': sck_ax = 0x500
            elif param[8] == 'YZ': sck_ax = 0x600
            else: sck_ax = 0x700

            if param[9] == '2k': sck_datakb = 0x800
            elif param[9] == '4k': sck_datakb = 0x1000
            elif param[9] == '8k': sck_datakb = 0x2000
            elif param[9] == '16k': sck_datakb = 0x4000
            else: sck_datakb = 0x8000

            sck_t = int(param[10], 10)

            thresh_acq = int(param[11], 10)
            if thresh_acq < 0x04B0: thresh_acq = 0x04B0
            elif thresh_acq > 0x1F40: thresh_acq = 0x1F40

            sample_activity = int(param[12], 10)
            if sample_activity < 0x0001: sample_activity = 0x0001
            elif sample_activity > 0x0010: sample_activity = 0x0010

            if param[13] == '2g': sck_g = 0x01
            elif param[13] == '4g': sck_g = 0x02
            else: sck_g = 0x04

            if param[14] == '12_5Hz': sck_freq = 0x08
            elif param[14] == '25Hz': sck_freq = 0x10
            elif param[14] == '50Hz': sck_freq = 0x20
            elif param[14] == '100Hz': sck_freq = 0x40
            else: sck_freq = 0x80

            if param[15] == 'ODR2': sck_bw = 0x100
            else: sck_bw = 0x200

            if param[16] == 'N': sck_pw = 0x400
            elif param[16] == 'L': sck_pw = 0x800
            else: sck_pw = 0x1000

            config_shm = acc | odr | ax | datakb
            send_frequency = sending_f | sync_f
            config_shm_sck = range_sck | acq_sck_odr | sck_ax | sck_datakb
            config_sck = sck_g | sck_freq | sck_bw | sck_pw

            config_str = bytes.fromhex(timestamp_str.replace('a1', 'a2') + '%04x' % config_shm + '%02x' % send_frequency + '%04x' % config_shm_sck + '%04x' % config_sck + '%04x' % sck_t + '%04x' % thresh_acq + '%04x' % sample_activity)
            self.device.send_data(self.remote_device, config_str) # Uilizzo l'oggetto remote_device e non la stringa
            status = 'Sent reconfiguration\n'
        else:
            self.device.send_data(self.remote_device, timestamp) # Uilizzo l'oggetto remote_device e non la stringa
            status = 'Sync sent\n'
        return status

    # Verifica se ci sono file che non sono stati chiusi, associati al dispositivo "addr".
    def check_files(self, addr, n_pack):
        status = ''
        if addr in self.open_file_dict:
            if n_pack < self.pack_num_dict[addr] + 1:
                with open(self.open_file_dict[addr], 'a') as f:
                    status = '\tAnomalous closure for data stream - %s\n' % self.open_file_dict[addr]
                    f.write('* INCOMPLETE TRANSMISSION *;')
                file2send = self.open_file_dict[addr].replace('/etc/config/scripts/SHM_Data/', '')
                if addr in self.file2s_dict:
                    self.file2s_dict[addr].append(file2send)
                else:
                    self.file2s_dict[addr] = [file2send]
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

    # Trasmette i dati, ricevuti dai sensori, al server tramite FTP.
    # Se per il sensore in esame ci sono piu file, li trasmette tutti.
    def send_file_to_server(self, addr):
        if addr in self.file2s_dict:
            return self.ftp_handler.upload_files(
                addr=addr,
                files_to_send=self.file2s_dict[addr],
                logger_callback=self.append_history
            )
        return ""
        
    """
        Gestore della coda: processa tutti i file in attesa per sensore
            - verifica se in file2s_influx_dict ci sono file per l'invio
            - per ogni file che trova chiama la worker create_influx_line_protocol
            - log e pulizia
    """
    def send_file_to_influx(self, addr):
        if addr in self.file2s_influx_dict:
            n_file = len(self.file2s_influx_dict[addr])
            
            for n in range(n_file):
                influx_status = self.create_influx_line_protocol(addr, self.file2s_influx_dict[addr][n])
                self.append_history("\t Influx: " + influx_status + "\n")
            self.file2s_influx_dict.pop(addr)

    """
        
    """
    def create_influx_line_protocol(self, addr, filename):
        # Estrazione data dal nome file: 0013a200..._Xaxis_27_10_2024_...
        date = "_".join(filename.split("_")[2:5])
        path = "/etc/config/scripts/SHM_Data/" + filename
        
        try:
            with open(path, 'r') as f:
                # RIGA 1: Parametri (ora; range; odr; asse;)
                parameters = f.readline().split(";")[:-1]
                
                # RIGA 2: Sincronizzazione (es: "Synced ")
                type_of_sync = f.readline().strip().split(" ")[:-1]
                
                # RIGA 3: Valori Medi (temp; m1; m2; m3;)
                mean_values = f.readline().split(";")[:-1]
                
                # RIGA 4: Salta la riga "First values"
                f.readline()
                
                # RIGA 5: I dati accelerometrici veri
                data = f.readline().split(";")[:-1]
                data_float = [float(x) for x in data if x.strip()]

            # --- LOGICA DI CALCOLO (Dal file di riferimento) ---
            m1, m2, m3 = float(mean_values[1]), float(mean_values[2]), float(mean_values[3])
            # Calcolo accelerazione totale efficace (RMS)
            accrms = sqrt(pow(m1, 2) + pow(m2, 2) + pow(m3, 2))
            # Calcolo angoli di inclinazione
            phi = degrees(atan2(m2, m1))
            theta = degrees(acos(m3 / accrms)) if accrms != 0 else 0
            
            # Gestione tempo e sincronizzazione
            timestamp_base = datetime.strptime(date + ' ' + parameters[0], '%d_%m_%Y %H:%M:%S')
            odr_val = float(parameters[2].replace(" Hz", ""))
            sync_bit = "1.0" if type_of_sync and type_of_sync[0] == "Synced" else "0.0"

            # --- PULIZIA PARAMETRI PER LINE PROTOCOL ---
            # I Tag non devono avere spazi. Trasformiamo "X axis" in "X" o "X_axis"
            clean_axis = parameters[3].replace(" axis", "").replace(" ", "_")
            clean_range = parameters[1].replace(" ", "")

            # --- COSTRUZIONE STRINGA INFLUX (Corretta) ---
            res = []
            # Struttura: measurement,tag1=val,tag2=val field1=val,field2=val timestamp
            # NOTA: Non ci devono essere spazi tra le virgole dei Tag o dei Field!
            base_str = (
                "WS_Test_Data,id={addr},axis={axis} "  # Tag (Spazio qui)
                "acc_range=\"{ar}\",temperature={temp},rms_x={rx},rms_y={ry},rms_z={rz}," # Field
                "phi={phi},theta={theta},issync={sync},peak_freq={pf},max_mag={mm},data={dat} {utime}" # Field (Spazio qui) Timestamp
            )

            for i, d in enumerate(data_float):
                utime = int((time.mktime(timestamp_base.timetuple()) + i / odr_val) * 1000)
                res.append(base_str.format(
                    addr=addr,
                    axis=clean_axis,
                    ar=clean_range,
                    temp=mean_values[0],
                    rx=m1, ry=m2, rz=m3,
                    phi=phi, theta=theta,
                    sync=sync_bit,
                    pf=self.fft_dict.get('peak_freq', -1),
                    mm=self.fft_dict.get('max_mag', -1),
                    dat=d,
                    utime=utime
                ))
            payload = '\n'.join(res)
            
            # --- INVIO HTTP POST ---
            headers = {'Content-Type': 'text/plain; charset=utf-8', 'Authorization': 'Token ' + self.influx_token}
            req = urllib.request.Request(self.influx_url, data=payload.encode('utf-8'), headers=headers, method='POST')
            
            with urllib.request.urlopen(req) as response:
                if response.status == 204:
                    return f"OK: {filename}"
                return f"Errore HTTP {response.status}"

        except Exception as e:
            return f"Errore: {str(e)}"
        
    # Scrive una stringa nel file "history.log".
    def append_history(self, stringa):
        with open(self.logger_file, 'a') as f:
            f.write(stringa)

    # Decodifica dei dati trasmessi dai sensori.
    def decode_payload(self, cut_payload, first):
        i = 0

        exp_mask = 0x7C00
        sign_mask = 0x8000
        mantissa_mask = 0x03FF
        small_number = 0.00006103515

        decoded_payload = []
        for _ in cut_payload:
            i = i + 1
            if i % 2 == 0:
                hex_char = (cut_payload[i - 2] << 8) | cut_payload[i - 1]
                if ((hex_char & exp_mask) >> 10) == 31:
                    if (hex_char & mantissa_mask) == 0:
                        my_float = float("inf")
                    else:
                        my_float = float("nan")
                elif ((hex_char & exp_mask) >> 10) == 0:
                    if (hex_char & mantissa_mask) == 0:
                        my_float = 0.0
                    else:
                        if ((hex_char & sign_mask) >> 15) == 0:
                            my_float = small_number * float((hex_char & mantissa_mask) / 1000.0)
                        else:
                            my_float = -1 * small_number * float((hex_char & mantissa_mask) / 1000.0)
                else:
                    if ((hex_char & sign_mask) >> 15) == 0:
                        my_float = pow(2, (((hex_char & exp_mask) >> 10) - 15)) * (1.0 + float((hex_char & mantissa_mask) / 1000.0))
                    else:
                        my_float = -1 * pow(2, (((hex_char & exp_mask) >> 10) - 15)) * (
                                1.0 + float((hex_char & mantissa_mask) / 1000.0))
                decoded_payload.append('{:8.6f}'.format(my_float + first))
        return decoded_payload

    # Funzione principale (main)
    def main(self):
        try:
            self.xbee_network = self.device.get_network() # Ottiene il device dalla rete XBee
            payload, address = self.get_data() # Attende un pacchetto dati.
            if payload is None or address is None:
                return  # Timeout o nessun dato, non processare
            self.check_device_config()  # Aggiorna le configurazioni dei dispositivi impostate dall'utente.
            self.process_data(payload, address) # Processa il pacchetto dati.
        except Exception as e:
            self.append_history("\tErrore generale nel main: %s\n" % str(e))

# Inizio del programma
if __name__ == "__main__":
    Gateway()
