import ctypes
from datetime import datetime, timezone

# Mappe per LETTURA (parsing package in ingresso)
rl = {0x01: '2g', 0x02: '4g', 0x03: '8g'}
ol = {0x07: '31.25 Hz', 0x06: '62.5 Hz', 0x05: '125 Hz', 0x04: '250 Hz', 0x03: '500 Hz'}
al = {0x01: ('Xaxis', 'X axis'), 0x02: ('Yaxis', 'Y axis'), 0x03: ('Zaxis', 'Z axis')}
sl = {0: 'Asynced', 1: 'Synced', 2: 'Synced2'}
class ProtocolDecoder:
    """
    Responsabile per la traduzione dal binario dei sensori a 
    un dizionario leggibile in python.
    """
    # Mapper pe la SCRITTURA (build pacchetti 0xA2)
    RANGE_MAP = {'2g': 0x01, '4g': 0x02, '8g': 0x04}
    ODR_MAP = {
        '31_25Hz': 0x08, '62_5Hz': 0x10, '125Hz': 0x20,
        '250Hz': 0x40, '500Hz': 0x80
    }
    AXIS_MAP = {
        'X': 0x100, 'Y': 0x200, 'Z': 0x400,
        'XY': 0x300, 'XZ': 0x500, 'YZ': 0x600
    }
    DATAKB_MAP = {'2k': 0x800, '4k': 0x1000, '8k': 0x2000, '16k': 0x4000}
    SEND_FREQ_MAP = {'1h': 0x0, '2h': 0x01, '3h': 0x02, '4h': 0x03, '6h': 0x04}
    SYNC_TYPE_MAP = {'SYNC1': 0x00}
    SCK_FREQ_MAP = {'12_5Hz': 0x08, '25Hz': 0x10, '50Hz': 0x20, '100Hz': 0x40}
    SCK_BW_MAP = {'ODR2': 0x100}
    SCK_PW_MAP = {'N': 0x400, 'L': 0x800}




    @staticmethod
    def build_sync_packet(delay):
        """
            Genera il pacchetto base di sincronizzazione (0xA1)
        """
        t = datetime.now(timezone.utc)

        # Timestamp: yy mm dd hh mm ss (6 bytes) + ms (2 byte) + delay (1 byte)
        ts_part = '%02d%02d%02d%02d%02d%02d%04x%02x' % (
            int(str(t.year)[-2:]), t.month, t.day, t.hour, t.minute, t.second, 
            int(t.microsecond / 1000), delay
        )
        return 'a1' + ts_part

    @staticmethod
    def build_config_packet(config_str, delay):
        """ 
            Genera il pacchetto di riconfigurazione (0xA2)
            Prende la stringa di configurazione dal config.txt 
        """
        t = datetime.now(timezone.utc)

        # 0. Parte comune di timestamp e sync
        ts_part = '%02d%02d%02d%02d%02d%02d%04x%02x' % (
            int(str(t.year)[-2:]), t.month, t.day, t.hour, t.minute, t.second, 
            int(t.microsecond / 1000), delay
        )
        # ts_part = '%02d%02d%02d%02d%02d%02d%04x%02x' % (
        #     int(str(t.year)[-2:]), t.month, t.day, t.hour, 55, t.second, 
        #     int(t.microsecond / 1000), delay
        # )

        param = config_str.split(' ')
        if len(param) < 17:                     #fallback a sync se parametri insufficienti
            return 'a1' + ts_part

        # Configurazione SHM
        acc = ProtocolDecoder.RANGE_MAP.get(param[0], 0x04)
        odr = ProtocolDecoder.ODR_MAP.get(param[1], 0x80)
        ax = ProtocolDecoder.AXIS_MAP.get(param[2], 0x700)
        datakb = ProtocolDecoder.DATAKB_MAP.get(param[3], 0x8000)
        # Frequenze
        sending_f = ProtocolDecoder.SEND_FREQ_MAP.get(param[4], 0x05)
        sync_f = ProtocolDecoder.SYNC_TYPE_MAP.get(param[5], 0x08)
        # Configurazione SHM per shock
        range_sck = ProtocolDecoder.RANGE_MAP.get(param[6], 0x04)
        acq_sck_odr = ProtocolDecoder.ODR_MAP.get(param[7], 0x80)
        sck_ax = ProtocolDecoder.AXIS_MAP.get(param[8], 0x700)
        sck_datakb = ProtocolDecoder.DATAKB_MAP.get(param[9], 0x8000)
        # Parametri numerici
        sck_t = int(param[10], 10)
        thresh_acq = max(0x4B0, min(int(param[11], 10), 0x1F40))
        sample_activity = max(0x0001, min(int(param[12], 10), 0x0010))
        # Configurazione HW schock
        sck_g = ProtocolDecoder.RANGE_MAP.get(param[13], 0x04)
        sck_freq = ProtocolDecoder.SCK_FREQ_MAP.get(param[14], 0x80)
        sck_bw = ProtocolDecoder.SCK_BW_MAP.get(param[15], 0x200)
        sck_pw = ProtocolDecoder.SCK_PW_MAP.get(param[16], 0x1000)
        # Costruzione maschere bitwise
        config_shm = acc | odr | ax | datakb
        send_frequency = sending_f | sync_f
        config_shm_sck = range_sck | acq_sck_odr | sck_ax | sck_datakb
        config_sck = sck_g | sck_freq | sck_bw | sck_pw

        # 2. Formattazione stringa HEX 
        # Formato: a2 + ts + shm(2b) + freq(1b) + shm_sck(2b) + sck_t(2b) + tresh(2b) + act(2b)
        config_hex = 'a2' + ts_part + '%04x%02x%04x%04x%04x%04x%04x' % (
            config_shm, send_frequency, config_shm_sck, 
            config_sck, sck_t, thresh_acq, sample_activity
        )

        return config_hex

    @staticmethod
    def decode_float_v2(high_byte, low_byte):
        """
            Decodifica due byte (high_byte e low_byte) in un valore floating-point a 16 bit.
        """
        # Maschere per estrazione esponente, mantissa e segno
        exp_mask, sign_mask, mantissa_mask = 0x7C00, 0x8000, 0x03FF

        small_number = 0.00006103515

        hex_char = (high_byte << 8) | low_byte                          #combina i due byte in un intero a 16 bit
        exponent = (hex_char & exp_mask) >> 10
        sign = -1 if (hex_char & sign_mask) else 1
        mantissa = (hex_char & mantissa_mask) / 1024.0

        if exponent == 31:
            return float('nan') if mantissa != 0 else float('inf')
        elif exponent == 0:
            return sign * small_number * mantissa if mantissa != 0 else 0.0
        return sign * (pow(2, exponent - 15) * (1.0 + mantissa))
    
    @classmethod
    def decode_samples(cls, raw_payload, first_value=0.0):
        """
        Decodifica una sequenza di campioni grezzi ricevuti dai sensori.
        
        Questa funzione elabora il payload grezzo proveniente dai sensori, ogni coppia
        di byte è convertita in un singolo valore floating-point utilizzando
        il metodo decode_float_v2. Per ogni campione decodificato, viene aggiunto
        un offset fornito da first_value per calibrazione o normalizzazione dei dati.
        
        Args:
            raw_payload (list): Lista di byte grezzi ricevuti dai sensori,
                               elaborata in coppie consecutive.
            first_value (float, optional): Valore di offset da aggiungere a ogni
                                          campione decodificato. Default è 0.0.
        
        Returns:
            list: Lista di stringhe rappresentanti i campioni decodificati,
                  formattati con 8 caratteri di larghezza e 6 decimali di precisione.
        
        Nota:
            - La funzione ignora il byte finale se raw_payload ha lunghezza dispari.
            - I campioni sono restituiti come stringhe formattate con padding.
        """
        samples = []
        for i in range(0, len(raw_payload), 2):
            if i+1 < len(raw_payload):
                val = cls.decode_float_v2(raw_payload[i], raw_payload[i+1])
                samples.append(f"{val + first_value:8.6f}")
        return samples
    
    @staticmethod
    def parse_sync_info(p):
        return {
            "datetime": f"{p[1]:x}-{p[2]:x}-{p[3]:x} {p[4]:x}:{p[5]:x}:{p[6]:x}",
            "battery": ((p[32] + (p[33] << 8)) * 0.001) if len(p) > 33 else None,
            "rssi": -p[34] if len(p) > 34 else None,
            "temp": ((p[35] + (p[36] << 8)) * 0.01) if len(p) > 36 else None,
            "humidity": ((p[37] + (p[38] << 8)) * 0.01) if len(p) > 38 else None,
            "reset_bit" : (p[39] + (p[40] << 8)) if len(p) > 40 else None,
            "gps_status": p[17],
            "errors":
                {"362": p[7], "355": p[8], "mem": p[9], "radio": p[10], "config": p[11]}
        }

    @staticmethod
    def parse_start_header(p):
        
        fx = ctypes.c_int32(ctypes.c_uint32(p[11]<<24|p[12]<<16|p[13]<<8|p[14]).value).value / 10000000.0
        fy = ctypes.c_int32(ctypes.c_uint32(p[15]<<24|p[16]<<16|p[17]<<8|p[18]).value).value / 10000000.0
        fz = ctypes.c_int32(ctypes.c_uint32(p[19]<<24|p[20]<<16|p[21]<<8|p[22]).value).value / 10000000.0

        axis_info = al.get(p[8], ('UnknownAxis', 'bad axis value'))
        return {
            "time": f"{p[3]:x}:{p[4]:x}:{p[5]:x}", "range": rl.get(p[6], "bad range"),
            "odr": ol.get(p[7], "bad ODR"), "axis_label": axis_info[0], "axis_file": axis_info[1],
            "sync": sl.get(p[9], "Unknown"), "baselines": (fx, fy, fz)
        }
    
    @staticmethod
    def parse_reduced_header(p):
        """Parsa l'header del pacchetto 0xD4 (dati ridotti)"""

        axis_info = al.get(p[8], ('UnknownAxis', 'bad axis value'))
        return {
            "time": f"{p[3]:x}:{p[4]:x}:{p[5]:x}",
            "range": rl.get(p[6], "bad range"),
            "odr": ol.get(p[7], "bad ODR"),
            "axis_file": axis_info[1],
            "sync": sl.get(p[9], "Unknown")
        }
    
    @staticmethod
    def parse_shock_header(p):
        "Parsa l'header del pachetto 0xC1 (evento shock)"
        return {
            "time": f"{p[1]:x}:{p[2]:x}:{p[3]:x}"
        }
    
    @staticmethod
    def get_packet_number(p):
        return (p[1] << 8) | p[2]
        