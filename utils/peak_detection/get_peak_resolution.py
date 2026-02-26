
import numpy
'''
    calcola la larghezza a meta ampiezza del picco
'''
def width_half_magnitude(magnitudes, peak_idx):
    half_max  = 0.707 * magnitudes[peak_idx]
    
    left = peak_idx
    while left > 0 and magnitudes[left] > half_max:
        left -= 1
    
    right = peak_idx
    while right < len(magnitudes) and magnitudes[right] > half_max:
        right += 1
    
    return right - left
    
    
'''
    Calcola la risoluzione tra due picchi:
    - rs > 1.5 => picchi separati
    - rs < 1.5 => il secondo potrebbe essere coda del primo
'''
def resolution(magnitudes, idx1, idx2):
    w1 = width_half_magnitude(magnitudes, idx1)
    w2 = width_half_magnitude(magnitudes, idx2)
    
    if w1 + w2 == 0:
        return
    
    rs = 1.18 * abs(idx2 - idx1) / (w1 + w2)
    
    return rs
    
'''
    Criteri di identificazione picco:
    - Massimo locale: x[i] e' picco solo se la sua magnitudo
        e' maggiore di quella dei suoi vicini
    - Soglia di Magnitudo: deve superare il threshold
    - Risoluzione >= 1.5
'''
def get_top_peaks_resolution(fft_res, fs, k=5):
    n = len(fft_res)
    half_len = n // 2
    
    # 1. calcolo magnitudo per half_len spettro
    magnitudes = [abs(fft_res[i]) for i in range(half_len)]
    frequencies = [i * (fs / n) for i in range(half_len)]
    
    # 2. calcolo soglia minima
    avg = numpy.mean(magnitudes)
    std = numpy.std(magnitudes)
    
    threshold = avg + 2 * std
    
    peaks = []
    
    while len(peaks) < k:
        max_val = -1
        max_idx = -1
        
        for j in range(1, half_len - 1):
            # CHECK massimo locale e soglia
            if magnitudes[j] > magnitudes[j-1] and magnitudes[j] > magnitudes[j+1]:
                if magnitudes[j] > max_val and magnitudes[j] > threshold:
                    max_val = magnitudes[j]
                    max_idx = j
            
        if max_idx != -1:
            
            # CHECK rs: picco sufficientemente separato da quelli trovati?
            is_separated = all(resolution(magnitudes, p["idx"], max_idx) >= 1.5
                            for p in peaks)
            
            if is_separated:
                freq = max_idx * (fs/n)
                peaks.append({"freq": freq, "mag": max_val, "idx": max_idx})
            
            # zeroing dell'intorno
            distance = frequencies[2] - frequencies[1]
            campioni_da_scartare = round((freq * 0.02) / distance)
            
            # EVITO DISTANZA MINIMA
            start = max(0, max_idx - campioni_da_scartare)
            end = min(half_len, max_idx + campioni_da_scartare + 1)
            
            for j in range(start, end):
                magnitudes[j] = 0
        else:
            break
    
    return peaks
