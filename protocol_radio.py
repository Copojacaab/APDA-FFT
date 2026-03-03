from digidevice import xbee

class XBeeManager:
    """
        Classe responsabile per la gestione fisica e logica della rete radio XBee.
    """

    def __init__(self, timeout = 5):
        self.device = None                                      # contiene: (MAC 64bit), (addr rete 16bit)
        self.network = None                                     # gestore della rete radio
        self.timeout = timeout

        # Rubrica: mac_stringa --> oggetto remote_device
        # STRUCT:
        # {
        # "0013a20041e7f6b7": <RemoteXBeeDevice object at 0x7f8b9c2a10>,
        # "0013a20041e7abcd": <RemoteXBeeDevice object at 0x7f8b9c2b50>,
        # "0013a20041e71234": <RemoteXBeeDevice object at 0x7f8b9c2c88>
        # }
        self._known_devices = {}
    
    def start(self, logger_callback):
        """
            Apre la comunicazione seriale con il modulo XBee locale
            e inizializza la rete
        """
        try:
            self.device = xbee.get_device()
            self.device.open()
            self.network = self.device.get_network()
            logger_callback("\t[Radio] Modulo Xbee avviato e rete inizializzata \n")
        except Exception as e:
            logger_callback(f"\t[Radio-ERROR] Impossibile avviare il modulo XBee: {str(e)}")
            raise               #sollevo eccezione (gw inutile)

    def stop(self, logger_callback):
        """
            Chiude la connessione
            da chiamare nel blocco finale del gw
        """
        if self.device and self.device.is_open():
            try:
                self.device.close()
                logger_callback("\t[Radio] Modulo XBee chiuso correttamente")
            except Exception as e:
                logger_callback(f"\t[Radio-ERROR] Errore durante la chiusura del modulo XBee: {str(e)}")

    def receive_data(self, logger_callback):
        """
            Si mette in ascolto per nuovi pacchetti
            
            Return: 
                tuple: (payload_list, address_str, payload_raw_bytes)
        """
        try:
            xbee_message = self.device.read_data(timeout=self.timeout)

            if xbee_message is None:
                return None, None, None
            
            remote_device = xbee_message.remote_device

            # estrazione indirizzo MAC pulito
            if hasattr(remote_device, 'get_64bit_addr'):
                addr = str(remote_device.get_64bit_addr()).lower()
            else:
                addr = str(remote_device).lower()
            
            # salvo/aggiorno il dispositivo nella rubrica
            self._known_devices[addr] = remote_device

            payload_bytes = xbee_message.data

            return list(payload_bytes), addr, payload_bytes
        except Exception as e:
            # ignoro i timeout
            if "timeout" not in str(e).lower():
                logger_callback(f"[Radio-ERRORE] errore in ricezione dati: {str(e)}")
            return None, None, None
    
    def send_data(self, addr, hex_payload, logger_callback):
        """
        Docstring for send_data
        
        :param addr: MAC address sensore
        :param hex_payload: payload da inviare
        """
        try:
            remote_device = self._get_remote_device(addr)

            if remote_device:
                payload_bytes = bytes.fromhex(hex_payload)
                self.device.send_data(remote_device, payload_bytes)
                return True
            else:
                logger_callback(f"\t[Radio-WARN] dispositivo non presente in rubrica: {addr}")
                return False
        except Exception as e:
            logger_callback(f"\t[Radio-ERROR] Errore durante l'invio al sensore {addr}: {str(e)}\n")
            return False
        
    def _get_remote_device(self, addr):
        """
            Recupera l'oggetto fisico del dispositivo dalla rubrica
        """
        return self._known_devices.get(addr)
