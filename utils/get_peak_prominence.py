import statistics


def calculate_prominence(magnitudes, peak_idx):
    peak_mag = magnitudes[peak_idx]
    
    # 1. CERCA LA VALLE A SINISTRA
    min_left = peak_mag
    for i in range(peak_idx - 1, -1, -1):
        if magnitudes[i] > peak_mag:
            # picco piu alto -> stop
            break
        if magnitudes[i] < min_left:
            # update del local min
            min_left = magnitudes[i]
            
    # 2. CERCA LA VALLE A DESTRA
    min_right = peak_mag
    for j in range(peak_idx + 1, len(magnitudes)):
        if magnitudes[j] > peak_mag:
            # picco piu alto -> stop
            break
        if magnitudes[j] < min_right:
            min_right = magnitudes[j]
            
    # prominence = distanza tra peak e valle piu alta
    return peak_mag - max(min_left, min_right)

def calculate_half_power_width(magnitudes, peak_idx, fs, n):
    # calcolo il livello bersaglio (-3db dal picco)
    target_mag = 0.707 * magnitudes[peak_idx]
    ds = fs/n                                                   #distanza tra due punti
    
    # cerco il punto a -3db (sx)
    left_idx = peak_idx
    while left_idx > 0 and magnitudes[left_idx] > target_mag:
        if magnitudes[left_idx - 1] > magnitudes[left_idx]:     # se stiamo ricominciando a salire
            break
        left_idx -= 1
        
    # cerco il punto a -3db (dx)
    right_idx = peak_idx
    while right_idx < len(magnitudes)-1 and magnitudes[right_idx] > target_mag:
        if magnitudes[right_idx + 1] > magnitudes[right_idx]: 
            break
        right_idx += 1
    
    # restituisco la larghezza in hz
    delta_f = (right_idx - left_idx) * ds
    return delta_f

def calculate_half_power_width_prominenceBased(magnitudes, prominence, peak_idx, fs, n):
    
    peak_mag = magnitudes[peak_idx]
    ds = fs / n
    valley = peak_mag - prominence
    
    # target a -3dB dalla vetta rispetto alla valle locale
    target_mag = valley + (prominence * 0.707)
    
    # -- CERCO PUNTO A -3dB a sx
    left_idx = peak_idx
    while left_idx > 0 and magnitudes[left_idx] > target_mag:
        if magnitudes[left_idx] > peak_mag:
            break
        left_idx -= 1
    
    # -- CERCO PUNTO A -3dB a dx
    right_idx = peak_idx
    while right_idx < len(magnitudes) - 1 and magnitudes[right_idx] > target_mag:
        if magnitudes[right_idx] > peak_mag:
            break
        right_idx += 1
    
    # Calcolo delta_f con failsafe: garantisce almeno la larghezza di 1 bin 
    # per evitare divisioni per zero nel calcolo del Q-factor
    bins_width = right_idx - left_idx
    if bins_width == 0:
        bins_width = 1
        
    delta_f = bins_width * ds
    return delta_f

def calculate_half_power_width_prominenceBased2(magnitudes, prominence, peak_idx, fs):
    n = len(magnitudes)
    peak_mag = magnitudes[peak_idx]
    ds = fs / n
    # valle base
    valley = peak_mag - prominence

    # calcolo l'half power sulla base della prominence
    # es: valley=3.4, prominence=0.6 => target = 3.4 + 0.6 *0.707 = 3.82
    target_mag = valley + (prominence * 0.707)
    
    # --CERCO PUNTO A -3db a sx
    left_idx = peak_idx
    while left_idx > 0 and magnitudes[left_idx] > target_mag:
        # sicurezza: stop se risaliamo su un altro picco
        if magnitudes[left_idx-1] > magnitudes[left_idx]:
            break
        left_idx -= 1
    
    # -- CERCO PUNTO A -3db a dx
    right_idx = peak_idx
    while right_idx < len(magnitudes) and magnitudes[right_idx] > target_mag:
        if magnitudes[right_idx + 1] > magnitudes[right_idx]:
            break
        right_idx += 1
    
    delta_f = (right_idx - left_idx) * ds
    return delta_f


def get_top_peaks_prominence(res_fft, fs, k=4):
    n = len(res_fft)
    half_len = n // 2
    
    MIN_DAMPING = 0.001             #0.1% filtra gli elettrici
    MAX_DAMPING = 0.06             #6% filtra rumore a banda larga
    # calcolo magnitudo e frequenze
    magnitudes = [abs(res_fft[i]) for i in range(half_len)]
    frequencies = [i * (fs/n) for i in range(half_len)]
    
    # calcolo threshold adattivo
    avg = statistics.mean(magnitudes)
    std = statistics.stdev(magnitudes)
    threshold = avg + 2 * std
    
    candidates = []
    
    # ricerca massimi locali
    for j in range(1, half_len-1):
        if magnitudes[j] > magnitudes[j-1] and magnitudes[j] > magnitudes[j+1]:
            if magnitudes[j] > threshold:
                
                # calcolo la prominence dell'ipotetico candidato
                prominence = calculate_prominence(magnitudes, j)
                
                if prominence > std:                                        #se ha un valore segnificativo aggiungo a candidati
                    # calcolo delta f
                    df_width = calculate_half_power_width_prominenceBased(magnitudes, prominence, j, fs, n)
                    
                    if df_width > 0:
                        # prendo la frequenza relativa al candidato
                        fn = frequencies[j]
                        # formula q-factor
                        q_factor = fn / df_width
                        
                        # conversione a smorzamento (damping factor)
                        damping = 1 / (2*q_factor)
                        
                        if MIN_DAMPING <= damping <= MAX_DAMPING:
                            candidates.append({
                                "freq": round(fn, 4),
                                "mag": round(magnitudes[j], 4),
                                "prominence": prominence,
                                "damping": round(damping * 100, 2),
                                "q-factor": round(q_factor, 2),
                                "idx": j
                            })
                    
    # ordino i candidati per magnitudo decrescente
    candidates = sorted(candidates, key=lambda x: x["mag"], reverse=True)
    
    # PARAMETRI DEL FILTRO
    EXCLUSION_RATIO = 0.15
    MIN_PROM_RATIO = 0.30
    
    final_peaks = []
    for cand in candidates:
        is_valid = True
        
        for accepted in final_peaks:
            # calcolo della distanza relativa rispetto al picco gia accettato
            rel_dist = abs(cand["freq"] - accepted["freq"]) / accepted["freq"]
            
            if rel_dist < EXCLUSION_RATIO: 
                # picco nella zona d'ombra di un picco gia' verificato, controllo il prominence to mag ratio
                prom_ratio = cand["prominence"] / cand["mag"]
                
                if prom_ratio < MIN_PROM_RATIO:
                    # spalla del picco principale => scarto
                    is_valid = False
                    break
        
        if is_valid:
            final_peaks.append(cand)
        
        if len(final_peaks) >= k:
            break
    
    return final_peaks