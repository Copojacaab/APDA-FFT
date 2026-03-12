import statistics

"""
    utils.get_peak_prominence
    Utility per la ricerca dei picchi pensato per l'applicazione a strutture flessibili (come passerelle)

    Implementa un approccio basato sulla prominenza dei picchi, valuta quanto un picco si innalza rispetto
    al rumore e alle valli intorno.
    Il sistema calcola lo smorzamento di ogni picco basandosi sulla larghezza a meta potenza, 
    adattando il target di -3dB in relazione alla prominenza del picco stesso (non alla magnitudo assoluto)
    
    Functions
    ---------
    calculate_prominence(magnitudes, peak_idx):
        calcola la prominence di un picco, prendendo la valle piu superficiale
    def calculate_half_power_width_prominenceBased(magnitudes, prominence, peak_idx, fs, n):
        calcola la larghezza di banda a meta potenza, adattando il magnitudo target in base alla prominence
    def get_top_peaks_prominence(res_fft, fs, k=4):
        funzione principale chiamata dal gateway. Esegue un ciclo per trovare i k picchi piu alti.
        restituisce una lista di dizionari con frequenza, magnitudo, prominence, smorzamento e q-factor del picco

"""


"""
    Params: 
        - magnitudes: lista di magnitudo (modulo FFT)
        - peak_idx: indice del picco di cui calcolare la prominence
    Returns: 
        - prominence: distanza tra il picco e la valle piu superficiale (float)
"""
def calculate_prominence(magnitudes, peak_idx):
    peak_mag = magnitudes[peak_idx]
    
    # Cerco il fondo a sinistra
    min_left = peak_mag
    for i in range(peak_idx - 1, -1, -1):
        if magnitudes[i] > peak_mag:
            # Trovato un picco più alto, mi fermo
            break
        if magnitudes[i] < min_left:
            min_left = magnitudes[i]
            
    # Cerco il fondo a destra
    min_right = peak_mag
    for j in range(peak_idx + 1, len(magnitudes)):
        if magnitudes[j] > peak_mag:
            # Trovato un picco più alto, mi fermo
            break
        if magnitudes[j] < min_right:
            min_right = magnitudes[j]
            
    # La prominence è la distanza tra la vetta e la valle più alta
    return peak_mag - max(min_left, min_right)

# def calculate_half_power_width(magnitudes, peak_idx, fs, n):
#     # Punto a -3dB dal picco
#     target_mag = 0.707 * magnitudes[peak_idx]
#     ds = fs/n                                                   
    
#     # Scendo a sinistra finché sto sopra i -3dB
#     left_idx = peak_idx
#     while left_idx > 0 and magnitudes[left_idx] > target_mag:
#         if magnitudes[left_idx - 1] > magnitudes[left_idx]:     # Se risale ho finito la "campana"
#             break
#         left_idx -= 1
        
#     # Scendo a destra
#     right_idx = peak_idx
#     while right_idx < len(magnitudes)-1 and magnitudes[right_idx] > target_mag:
#         if magnitudes[right_idx + 1] > magnitudes[right_idx]: 
#             break
#         right_idx += 1
    
#     return (right_idx - left_idx) * ds



"""
    Params: 
        - magnitudes: lista di magnitudo
        - prominence: prominence del picco 
        - peak_idx: indice del picco da analizzare
        - fs; frequenza di campionamento
        - n: numero campioni
    Returns: 
        - width; bandwith a meta potenza (float)
"""
def calculate_half_power_width_prominenceBased(magnitudes, prominence, peak_idx, fs, n):
    peak_mag = magnitudes[peak_idx]
    ds = fs / n
    valley = peak_mag - prominence
    
    # Target a -3dB calcolato rispetto alla base del picco (non allo zero)
    target_mag = valley + (prominence * 0.707)
    
    left_idx = peak_idx
    while left_idx > 0 and magnitudes[left_idx] > target_mag:
        if magnitudes[left_idx] > peak_mag:
            break
        left_idx -= 1
    
    right_idx = peak_idx
    while right_idx < len(magnitudes) - 1 and magnitudes[right_idx] > target_mag:
        if magnitudes[right_idx] > peak_mag:
            break
        right_idx += 1
    
    # Se i bin sono uguali metto 1 per non far schiantare il Q-factor dopo
    bins_width = max(right_idx - left_idx, 1)
    
    return bins_width * ds




# def calculate_half_power_width_prominenceBased2(magnitudes, prominence, peak_idx, fs):
#     n = len(magnitudes)
#     peak_mag = magnitudes[peak_idx]
#     ds = fs / n
#     valley = peak_mag - prominence
#     target_mag = valley + (prominence * 0.707)
    
#     left_idx = peak_idx
#     while left_idx > 0 and magnitudes[left_idx] > target_mag:
#         if magnitudes[left_idx-1] > magnitudes[left_idx]:
#             break
#         left_idx -= 1
    
#     right_idx = peak_idx
#     while right_idx < len(magnitudes) and magnitudes[right_idx] > target_mag:
#         if magnitudes[right_idx + 1] > magnitudes[right_idx]:
#             break
#         right_idx += 1
    
#     return (right_idx - left_idx) * ds



"""
    Params: 
        - res_fft: raw FFT (array di numeri complessi)
        - fs: ''
        - k: numero di picchi da resituire (default 4)
    Returns:
        - final_peaks: lista di dict con frequenza, magnitudo, prominence, smorzamento
            e q-factor dei picchi
"""
def get_top_peaks_prominence(res_fft, fs, k=4):
    n = len(res_fft)
    half_len = n // 2
    
    # Range di smorzamento accettabile
    # - 0.1%: frequenze elettriche
    # - 7%: damping per strutture fisiche (0,5% - 5%) 
    MIN_DAMPING = 0.001             
    MAX_DAMPING = 0.07            
    
    magnitudes = [abs(res_fft[i]) for i in range(half_len)]
    frequencies = [i * (fs/n) for i in range(half_len)]
    
    # Soglia dinamica per rumore di fondo
    avg = statistics.mean(magnitudes)
    std = statistics.stdev(magnitudes)
    threshold = avg + 2 * std
    
    candidates = []
    
    # Cerco massimi locali sopra la soglia
    for j in range(1, half_len-1):
        if magnitudes[j] > magnitudes[j-1] and magnitudes[j] > magnitudes[j+1]:
            if magnitudes[j] > threshold:
                
                prominence = calculate_prominence(magnitudes, j)
                
                # se il picco spunta abbastanza
                if prominence > (0.5 * std):                                        
                    df_width = calculate_half_power_width_prominenceBased(magnitudes, prominence, j, fs, n)
                    
                    if df_width > 0:
                        fn = frequencies[j]
                        q_factor = fn / df_width
                        damping = 1 / (2*q_factor)                  #0.5=smorzamento critico, 0.1=smorzamento leggero
                        
                        # Controllo se lo smorzamento ha senso (filtro sporcizia elettrica e rumore ambientale)
                        if MIN_DAMPING <= damping <= MAX_DAMPING:
                            candidates.append({
                                "freq": round(fn, 4),
                                "mag": round(magnitudes[j], 4),
                                "prominence": prominence,
                                "damping": round(damping * 100, 2),
                                "q-factor": round(q_factor, 2),
                                "idx": j
                            })
                    
    # Ordino per ampiezza decrescente
    candidates = sorted(candidates, key=lambda x: x["mag"], reverse=True)
    
    EXCLUSION_RATIO = 0.05                                  #finestra di vicinanza
    MIN_PROM_RATIO = 0.10                                   #rapporto tra prominence e magnitudo
    
    # ricerca dei k picchi piu importanti
    # esclusione gobbe
    final_peaks = []
    for cand in candidates:
        is_valid = True
        
        for accepted in final_peaks:
            # Calcolo la distanza relativa tra il candidato e tutti gli accettati
            rel_dist = abs(cand["freq"] - accepted["freq"]) / accepted["freq"]
            
            # check distanza relativa
            if rel_dist < EXCLUSION_RATIO: 
                
                prom_ratio = cand["prominence"] / cand["mag"]   #calcolo rapporto tra prom e mag
                if prom_ratio < MIN_PROM_RATIO:                 #se spicca poco => gobba
                    is_valid = False
                    break
        
        if is_valid:
            final_peaks.append(cand)
        
        if len(final_peaks) >= k:
            break
    
    return final_peaks