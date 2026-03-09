import ftplib
import os


"""
    utils.ftp_manager: 
        - gestisce la connessione FTP e l'upload dei file al server
        - rimuove i file dalla memoria del gateway dopo l'upload
"""
class FTPClient:
    def __init__(self, server, user, pwd, path, local_dir):
        self.server = server                    #ftp.wisepower.it
        self.user = user                        #1451303@aruba.it
        self.pwd = pwd                          #password   
        self.path = path                        #www.wisepower.it/SHM_Files/Test_Ufficio
        self.local_dir = local_dir              #/etc/config/scripts/SHM_Data/
        
    """
        Spedisce la lista dei file per un determinato sensore al server FTP.

        Params: 
            - addr: MAC
            - files_to_send: lista dei file da spedire (un sensore per chiamata)
        Returns:
            - status: stringa errore o vuota se ok
    """
    def upload_files(self, addr, files_to_send, logger_callback):
        
        
        try: 
            logger_callback(f"\t [FTP] Tentativo di connessione a {self.server}...\n")
            if not files_to_send:
                return ""
            
            status = ""
            try:
                # Apro la sessione e mi connetto
                session = ftplib.FTP()
                session.connect(self.server, 21, 60.0)
                session.login(self.user, self.pwd)
                session.cwd(self.path)

                # Ciclo di invio sui file
                while files_to_send:
                    filename = files_to_send[0]

                    if not filename:
                        logger_callback(f"\t[FTP] Nome file vuoto per {addr}, salto\n")
                        files_to_send.pop(0)
                        continue

                    full_local_path = os.path.join(self.local_dir, filename)

                    if not os.path.exists(full_local_path):
                        logger_callback(f"\t[FTP] File {filename} non trovato in locale\n")
                        files_to_send.pop(0)
                        continue
                        
                    # INVIO EFFETTIVO
                    with open(full_local_path, 'rb') as file:
                        session.storbinary(f'STOR {filename}', file)
                        
                    # Se l'upload è andato, cancello il file locale per non ingolfare il GW
                    os.remove(full_local_path)
                    logger_callback(f"\t[FTP] File {filename} trasferito e rimosso correttamente\n")
                    
                    files_to_send.pop(0)
                
                session.close()
                status=""
            except Exception as e:
                status = str(e)
                logger_callback(f"\t[FTP] Errore durante l'upload per {addr}: {status}")
            
            return status
        except Exception as e:
            logger_callback(f"\t [FTP-ERROR] Errore: {str(e)}")