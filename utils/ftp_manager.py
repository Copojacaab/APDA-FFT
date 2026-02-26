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
        # Spedisce la lista di file al server e pulisce la cartella locale
        
        if not files_to_send:
            return ""
        
        status = ""
        try:
            # Apro la sessione e mi connetto
            session = ftplib.FTP()
            session.connect(self.server, 21, 60.0)
            session.login(self.user, self.pwd)
            session.cwd(self.path)
            
            # Giro sui file che mi sono stati passati
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
                    
                # INVIO EFFETTIVO
                with open(full_local_path, 'rb') as file:
                    session.storbinary(f'STOR {filename}', file)
                    
                # Se l'upload è andato, cancello il file locale per non ingolfare il GW
                os.remove(full_local_path)
                logger_callback(f"[FTP] File {filename} trasferito e rimosso correttamente")
                
                files_to_send.pop(0)
            
            session.close()
            status=""
        except Exception as e:
            status = str(e)
            logger_callback(f"\t[FTP] Errore durante l'upload per {addr}: {status}")
        
        return status