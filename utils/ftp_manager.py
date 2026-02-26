import ftplib
import os


class FTPClient:
    def __init__(self, server, user, pwd, path, local_dir):
        self.server = server
        self.user = user
        self.pwd = pwd
        self.path = path
        self.local_dir = local_dir
        
    def upload_files(self, addr, files_to_send, logger_callback):
        """_summary_
            Gestisce l'upload di una lista di file
        Args:
            addr : indirizzo del sensore 
            files_to_send (_type_): lista di nomi di file da caricare
            logger_callback (_type_): funzione per scrivere nell'history.log del gw
        """
        
        if not files_to_send:
            return ""
        
        status = ""
        try:
            # crezione sessione e connessione
            session = ftplib.FTP()
            session.connect(self.server, 21, 60.0)
            session.login(self.user, self.pwd)
            session.cwd(self.path)
            
            # itero sui file preenti nella lista
            while files_to_send:
                filename = files_to_send[0]
                
                if not filename:
                    logger_callback(f"\t[FTP] Nome file vuoto per {addr}, salto")
                    files_to_send.pop(0)
                    continue
                
                full_local_path = os.path.join(self.local_dir, filename)
                
                if not os.path.exists(full_local_path):
                    logger_callback(f"\t[FTP] File {filename} non trovato in locale")
                    files_to_send.pop(0)
                    continue
                    
                # UPLOAD
                with open(full_local_path, 'rb') as file:
                    session.storbinary(f'STOR {filename}', file)
                    
                # rimozione file locale
                os.remove(full_local_path)
                logger_callback(f"[FTP] File {filename} trasferito e rimosso correttamnte")
                
                files_to_send.pop(0)
            
            session.close()
            status=""
        except Exception as e:
            status = str(e)
            logger_callback(f"\t[FTP] Errore durante l'upload per {addr}: {status}")
        
        return status