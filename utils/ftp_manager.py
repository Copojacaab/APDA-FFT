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
        self.user = user                        #REDACTED
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
        # Spedisce la lista di file al server e pulisce la cartella locale
        
        uploaded_successfully = []
        logger_callback(f"\t[FTP] Tentativo di connessione a {self.server}...\n")
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
            for filename in list(files_to_send):
                full_local_path = os.path.join(self.local_dir, filename)

                try:
                    with open(full_local_path, 'rb') as f:
                        session.storbinary(f'STOR {filename}', f)
                    
                    uploaded_successfully.append(filename)
                    logger_callback(f"\t[FTP] File {filename} trasferito con successo\n")
                except Exception as e:
                    logger_callback(f"[FTP] Errore su {filename}: {str(e)}\n")
                    return []

            session.close()
        except Exception as e:
            status = str(e)
            logger_callback(f"\t[FTP] Errore durante l'upload per {addr}: {status}")
            return []
        
        return uploaded_successfully