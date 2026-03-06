import statistics

"""
utils.get_peak_resolution
Utility per la ricerca dei picchi pensato per l'applicazione a strutture rigide (come gallerie).

Implementa un approccio basato sulla capacita' di distinguere tra frequenze molto vicine tra loro.
Functions
---------
width_half_magnitude(magnitudes, peak_idx)
    Calcola la larghezza del picco nel punto di mezza potenza (a -3db dalla cima).
resolution(magnitudes, idx1, idx2)
    Applica la formula di risoluzione, se il valore ottenuto e' inferiore a 1.5 i picchi
    sono considerati troppo vicini per essere riconoscibili (ne scarto uno)
get_top_peaks_resolution(fft_res, fs, k=5)
    Funzione principale chiamata dal gateway. Esegue un ciclo per trovare ik picchi piu' alti,
    assicurandosi che ognuno sia separato dagli altri secondo il criterio di risoluzione.
    Restituisce una lista di dizionari con frequenza, magnitudo e indice del picco
Note
-----
-   Tutte i mangnitudi sono espressi un numeri complessi (raw FFT) per la conversione
        moltiplicare per (fs / n) -> n=numero campioni.
-   0.707 = mezza potenza, 
    1.18 = fattore di normalizzazione (gaussiani)
    1.5 = soglia minima
    2% = distanza minima tra i picchi
"""


def width_half_magnitude(magnitudes, peak_idx):
    """
        Calcola la larghezza del picco nel punto di mezza potenza (a -3db dalla cima)
    """
    half_max  = 0.707 * magnitudes[peak_idx]
    
    left = peak_idx
    while left > 0 and magnitudes[left] > half_max:
        left -= 1
    
    right = peak_idx
    while right < len(magnitudes) and magnitudes[right] > half_max:
        right += 1
    
    return right - left
    
    

def resolution(magnitudes, idx1, idx2):
    """
        Verifica se due picchi sono distinguibili secondo la fomula di riswsoluzione
    """
    w1 = width_half_magnitude(magnitudes, idx1)
    w2 = width_half_magnitude(magnitudes, idx2)
    
    if w1 + w2 == 0:
        return 0
    
    # x: abs(idx2-idx1) = quanto sono distanti i centri dei picchi
    # y: (w1+w2) = quanto sono larghi i picchi
    # x/y =  separazione/larghezza (si fondono?)
    rs = 1.18 * abs(idx2 - idx1) / (w1 + w2)
    return rs
    


"""
    Parameters
        - fft_res: risultato grezzo della FFT (array numeri complessi), vengono considerate solo
        le frequenze positive, usata per estrarre il magnitudo
        - fs: frequenza di campionamento (in Hz)
        - k: numero massimo di picchi da restituire (default 5)
    Behavior
        - Calcolo magnitudo e threshold dinamico per esclusione del rumore di fondo
        - Ricerca iterativa del picco piu alto, calcolo della larghezza a meta potenza (widh_half_magnitude())
            applicazione del criterio di risoluzione (resolution()) e confronto con quelli gia salvati
        - Un candidato viene accettato solo se il suo valore di risoluzione rispetto a tutti i picchi gia'
            salvati e' >= 1.5 (altrimenti e' troppo vicino a un picco gia' considerato)
        - Dopo aver accettato un picco, si azzerano i magnitudi nei dintorni di quel picco
"""
def get_top_peaks_resolution(fft_res, fs, k=5):
    n = len(fft_res)
    half_len = n // 2
    
    magnitudes = [abs(fft_res[i]) for i in range(half_len)]
    frequencies = [i * (fs / n) for i in range(half_len)]
    
    # Soglia minima per non prendere il rumore di fondo
    avg = statistics.mean(magnitudes)
    std = statistics.stdev(magnitudes)
    threshold = avg + 2 * std
    
    peaks = []
    
    while len(peaks) < k:
        max_val = -1
        max_idx = -1
        
        # Ricerca del picco piu' alto iterativo
        for j in range(1, half_len - 1):
            if magnitudes[j] > magnitudes[j-1] and magnitudes[j] > magnitudes[j+1]:
                if magnitudes[j] > max_val and magnitudes[j] > threshold:
                    max_val = magnitudes[j]
                    max_idx = j

        freq = max_idx * (fs/n)
        
        if max_idx != -1:
            # Controllo se il nuovo picco è abbastanza lontano da quelli già salvati
            is_separated = all(resolution(magnitudes, p["idx"], max_idx) >= 1.5
                            for p in peaks)
            
            if is_separated:
                peaks.append({"freq": freq, "mag": max_val, "idx": max_idx})
            
            # Azzero la zona intorno al picco trovato per cercare il prossimo
            distance = frequencies[2] - frequencies[1]
            campioni_da_scartare = round((freq * 0.02) / distance) # Intorno del 2%
            
            start = max(0, max_idx - campioni_da_scartare)
            end = min(half_len, max_idx + campioni_da_scartare + 1)
            
            for j in range(start, end):
                magnitudes[j] = 0
        else:
            # Non ci sono più picchi sopra la soglia
            break
    
    return peaks