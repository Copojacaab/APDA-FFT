import statistics

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
            
    # La prominence è la distanza tra la vetta e la valle più "superficiale"
    return peak_mag - max(min_left, min_right)

def calculate_half_power_width(magnitudes, peak_idx, fs, n):
    # Punto a -3dB dal picco
    target_mag = 0.707 * magnitudes[peak_idx]
    ds = fs/n                                                   
    
    # Scendo a sinistra finché sto sopra i -3dB
    left_idx = peak_idx
    while left_idx > 0 and magnitudes[left_idx] > target_mag:
        if magnitudes[left_idx - 1] > magnitudes[left_idx]:     # Se risale ho finito la "campana"
            break
        left_idx -= 1
        
    # Scendo a destra
    right_idx = peak_idx
    while right_idx < len(magnitudes)-1 and magnitudes[right_idx] > target_mag:
        if magnitudes[right_idx + 1] > magnitudes[right_idx]: 
            break
        right_idx += 1
    
    return (right_idx - left_idx) * ds

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

def calculate_half_power_width_prominenceBased2(magnitudes, prominence, peak_idx, fs):
    n = len(magnitudes)
    peak_mag = magnitudes[peak_idx]
    ds = fs / n
    valley = peak_mag - prominence
    target_mag = valley + (prominence * 0.707)
    
    left_idx = peak_idx
    while left_idx > 0 and magnitudes[left_idx] > target_mag:
        if magnitudes[left_idx-1] > magnitudes[left_idx]:
            break
        left_idx -= 1
    
    right_idx = peak_idx
    while right_idx < len(magnitudes) and magnitudes[right_idx] > target_mag:
        if magnitudes[right_idx + 1] > magnitudes[right_idx]:
            break
        right_idx += 1
    
    return (right_idx - left_idx) * ds


def get_top_peaks_prominence(res_fft, fs, k=4):
    n = len(res_fft)
    half_len = n // 2
    
    # Range di smorzamento accettabile
    MIN_DAMPING = 0.001             
    MAX_DAMPING = 0.06             
    
    magnitudes = [abs(res_fft[i]) for i in range(half_len)]
    frequencies = [i * (fs/n) for i in range(half_len)]
    
    # Soglia dinamica basata su media e 2 sigma
    avg = statistics.mean(magnitudes)
    std = statistics.stdev(magnitudes)
    threshold = avg + 2 * std
    
    candidates = []
    
    # Cerco massimi locali sopra la soglia
    for j in range(1, half_len-1):
        if magnitudes[j] > magnitudes[j-1] and magnitudes[j] > magnitudes[j+1]:
            if magnitudes[j] > threshold:
                
                prominence = calculate_prominence(magnitudes, j)
                
                # Se il picco "spunta" abbastanza rispetto al rumore (std) lo tengo
                if prominence > std:                                        
                    df_width = calculate_half_power_width_prominenceBased(magnitudes, prominence, j, fs, n)
                    
                    if df_width > 0:
                        fn = frequencies[j]
                        q_factor = fn / df_width
                        damping = 1 / (2*q_factor)
                        
                        # Controllo se lo smorzamento ha senso (filtro sporcizia elettrica o larga banda)
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
    
    # Filtro per picchi troppo vicini
    EXCLUSION_RATIO = 0.15
    MIN_PROM_RATIO = 0.30
    
    final_peaks = []
    for cand in candidates:
        is_valid = True
        
        for accepted in final_peaks:
            # Se è troppo vicino a un picco già preso, controllo se è un picco vero o una "spalla"
            rel_dist = abs(cand["freq"] - accepted["freq"]) / accepted["freq"]
            
            if rel_dist < EXCLUSION_RATIO: 
                # Se la prominence rispetto alla magnitudo è bassa, è probabilmente un lobo secondario
                prom_ratio = cand["prominence"] / cand["mag"]
                if prom_ratio < MIN_PROM_RATIO:
                    is_valid = False
                    break
        
        if is_valid:
            final_peaks.append(cand)
        
        if len(final_peaks) >= k:
            break
    
    return final_peaks