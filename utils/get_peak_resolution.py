import statistics

# Calcola la larghezza a -3dB (metà potenza)
def width_half_magnitude(magnitudes, peak_idx):
    half_max  = 0.707 * magnitudes[peak_idx]
    
    left = peak_idx
    while left > 0 and magnitudes[left] > half_max:
        left -= 1
    
    right = peak_idx
    while right < len(magnitudes) and magnitudes[right] > half_max:
        right += 1
    
    return right - left
    
    
# Verifica se due picchi sono distinguibili (Criterio di risoluzione)
# Se rs < 1.5 sono troppo fusi insieme
def resolution(magnitudes, idx1, idx2):
    w1 = width_half_magnitude(magnitudes, idx1)
    w2 = width_half_magnitude(magnitudes, idx2)
    
    if w1 + w2 == 0:
        return 0
    
    rs = 1.18 * abs(idx2 - idx1) / (w1 + w2)
    return rs
    
# Cerca i migliori K picchi usando il criterio della risoluzione
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
        
        # Trovo il massimo assoluto corrente nello spettro (che sia un picco locale)
        for j in range(1, half_len - 1):
            if magnitudes[j] > magnitudes[j-1] and magnitudes[j] > magnitudes[j+1]:
                if magnitudes[j] > max_val and magnitudes[j] > threshold:
                    max_val = magnitudes[j]
                    max_idx = j
            
        if max_idx != -1:
            # Controllo se il nuovo picco è abbastanza lontano da quelli già salvati
            is_separated = all(resolution(magnitudes, p["idx"], max_idx) >= 1.5
                            for p in peaks)
            
            if is_separated:
                freq = max_idx * (fs/n)
                peaks.append({"freq": freq, "mag": max_val, "idx": max_idx})
            
            # "Azzero" la zona intorno al picco trovato per cercare il prossimo
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