import cmath
import statistics


def remove_dc_component(samples):
    """centratura del segnale"""
    if not samples:
        return samples
    
    median = statistics.median(samples)
    return [x-median for x in samples]

def pad(lst):
    '''padding della lista alla potenza di 2 piu vicina'''
    k = 0
    while 2**k < len(lst):
        k += 1
        
    zeros = [0] * (2**k - len(lst))
        

    return lst + zeros

def bit_reversal(x):
    """Riordina la lista secondo la permutazione bit-reversal."""
    n = len(x)
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j ^= bit
        if i < j:
            x[i], x[j] = x[j], x[i]
    return x

def fft(x):
    """FFT Radix-2 Iterativa (Decimation-in-Time)."""
    n = len(x)
    # bit-reversal (per lavorare in place)
    x = bit_reversal(x)
    
    # cicli principali della fft
    # stadio (log2 n stadi totali)
    s = 1
    while (1 << s) <= n:
        m = 1 << s        # lunghezza del sottoproblema corrente (2, 4, 8...)
        m2 = m >> 1       # meta lunghezza (distanza tra i rami della farfalla)
        
        # twiddle factor
        # omega_m = e^(-j * 2pi / m)
        w_m = cmath.exp(-2.0j * cmath.pi / m)
        
        # itera sui blocchi di dimensione m
        for k in range(0, n, m):
            w = 1.0 + 0j  # inizializza twiddle factor per il blocco
            
            # operazione a farfalla (butterfly)
            for j in range(m2):
                u = x[k + j]
                v = x[k + j + m2] * w
                
                x[k + j] = u + v
                x[k + j + m2] = u - v
                
                # aggiorna il twiddle factor per il prossimo bin del blocco
                w *= w_m
        s += 1
    return x



def start_fft(samples, fs):
    
    # 1. CENTRATURA
    samples_centered = remove_dc_component(samples)
    
    # 2. PADDING potenza di 2
    samples_padded = pad(samples_centered)
    
    # 3. FFT
    res = fft(samples_padded)
    
    res[0] = 0          # scarto dc

    return res          # da prendere portanti con get_peak
   

# def main():
#     print(timeit.repeat(lambda:flow(), repeat= 5, number=1))

# if __name__ == "__main__":
#     main()