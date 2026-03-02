import ctypes

class ProtocolDecoder:
    """
    Responsabile per la traduzione dal binario dei sensori a 
    un dizionario leggibile in python.
    """
    RANGE_MAP = {'2g': 0x01, '4g': 0x02, '8g': 0x03}
    ODR_MAP = {
        '31_25Hz': 0x08, '62_5hz': 0x10, '125Hz': 0x20,
        '250Hz': 0x40, '500Hz': 0x80
    }
    AXIS_MAP = {
        'X': 0x100, 'Y': 0x200, 'Z': 0x400,
        'XY': 0x300, 'XZ': 0x500, 'XYZ': 0x600
    }
    DATAKB_MAP = {'2k': 0x800, '4k': 0x1000, '8k': 0x2000, '16k': 0x4000}
    SEND_FREQ_MAP = {'1h': 0x0, '2h': 0x01, '3h': 0x02, '4h': 0x03, '6h': 0x04}
    SYNC_TYPE_MAP = {'SYNC1': 0x00}
    SCK_FREQ_MAP = {'12_5Hz': 0x08, '25Hz': 0x10, '50Hz': 0x20, '100Hz': 0x40}
    SCK_BW_MAP = {'ODR2': 0x100}
    SCK_PW_MAP = {'N': 0x400, 'L': 0x800}

    @staticmethod
    def decode_float_v2(high_byte, low_byte):
        exp_mask, sign_mask, mantissa_mask = 0x7C00, 0x8000, 0x03FF
        small_number = 0.00006103515
        hex_char = (high_byte << 8) | low_byte
        exponent = (hex_char & exp_mask) >> 10
        sign = -1 if (hex_char & sign_mask) else 1 
        mantissa = (hex_char & mantissa_mask) / 1000.0

        if exponent == 31:
            return float('nan') if mantissa != 0 else float('inf')
        elif exponent == 0:
            return sign * small_number * mantissa if mantissa != 0 else 0.0
        return sign * (pow(2, exponent - 15) * (1.0 + mantissa))
    
    @classmethod
    def decode_samples(cls, raw_payload, first_value=0.0):
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
        rl = {0x01: '2g', 0x02: '4g', 0x03: '8g'}
        ol = {0x07: '31.25 Hz', 0x06: '62.5 Hz', 0x05: '125 Hz', 0x04: '250 Hz', 0x03: '500 Hz'}
        al = {0x01: ('Xaxis', 'X axis'), 0x02: ('Yaxis', 'Y axis'), 0x03: ('Zaxis', 'Z axis')}
        sl = {0: 'Asynced', 1: 'Synced', 2: 'Synced2'}
        
        fx = ctypes.c_int32(ctypes.c_uint32(p[11]<<24|p[12]<<16|p[13]<<8|p[14]).value).value / 10000000.0
        fy = ctypes.c_int32(ctypes.c_uint32(p[15]<<24|p[16]<<16|p[17]<<8|p[18]).value).value / 10000000.0
        fz = ctypes.c_int32(ctypes.c_uint32(p[19]<<24|p[20]<<16|p[21]<<8|p[22]).value).value / 10000000.0

        axis_info = al.get(p[8], ('UnknownAxis', 'bad axis value'))
        return {
            "time": f"{p[3]:x}:{p[4]:x}:{p[5]:x}", "range": rl.get(p[6], "bad range"),
            "odr": ol.get(p[7], "bad ODR"), "axis_label": axis_info[0], "axis_file": axis_info[1],
            "sync": sl.get(p[9], "Unknown"), "baselines": (fx, fy, fz)
        }

def test_float_parity():
    # Coppiette di byte (High, Low) e risultato atteso (se noto)
    test_cases = [
        ([0x3C, 0x00], 1.0),      # Esempio: valore unitario
        ([0xBC, 0x00], -1.0),     # Esempio: valore unitario negativo
        ([0x42, 0x00], 4.0),      # Esponente positivo
        ([0x00, 0x00], 0.0),      # Zero
        ([0x7C, 0x00], float('inf')) # Infinito
    ]
    
    print(f"{'Hex':<10} | {'Vecchia':<10} | {'Nuova':<10} | {'Esito'}")
    print("-" * 50)
    
    for bytes_in, expected in test_cases:
        # Vecchia logica (estratta dal file originale)
        hex_char = (bytes_in[0] << 8) | bytes_in[1]
        old_val = pow(2, ((hex_char & 0x7C00) >> 10) - 15) * (1.0 + (hex_char & 0x03FF) / 1000.0)
        if hex_char & 0x8000: old_val *= -1
        
        # Nuova logica
        new_val = ProtocolDecoder.decode_float_v2(bytes_in[0], bytes_in[1])
        
        match = "OK" if str(old_val) == str(new_val) else "ERRORE"
        print(f"{bytes_in[0]:02x}{bytes_in[1]:02x}     | {old_val:<10.4f} | {new_val:<10.4f} | {match}")

test_float_parity()