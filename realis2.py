import itertools
import ctypes
import os
import sys
import time
import base64
import multiprocessing
import json
import math

# Cek library psutil untuk monitor CPU
try:
    import psutil
    PSUTIL_AVAIL = True
except ImportError:
    PSUTIL_AVAIL = False

# ==============================================================================
# ⚙️ KONFIGURASI
# ==============================================================================
LIB_PATH = "./solver_lib.so"
KEYS_FILE = "keys-input.txt"
MESSAGE_FILE = "message.b64"
FILE_LOG_SUCCESS = "found.log"
FILE_CHECKPOINT = "checkpoint.json"

# BATCH SIZE: Jumlah password per update speed.
# Tetap kecil (50) agar Speedometer jalan mulus.
BATCH_SIZE = 50 

# ==============================================================================
# GLOBAL SHARED VARIABLES
# ==============================================================================
shared_lib = None
shared_salt = None
shared_cipher = None
shared_cipher_len = None

def init_worker(salt_raw, cipher_raw):
    """Inisialisasi Worker: Load Lib & Data Read-Only"""
    global shared_lib, shared_salt, shared_cipher, shared_cipher_len
    
    try:
        shared_lib = ctypes.CDLL(LIB_PATH)
        # Definisi ulang tipe argumen agar sesuai dengan Go Hybrid/Fixed
        shared_lib.CheckPassword.argtypes = [
            ctypes.c_char_p, 
            ctypes.POINTER(ctypes.c_ubyte), 
            ctypes.POINTER(ctypes.c_ubyte), 
            ctypes.c_int
        ]
        shared_lib.CheckPassword.restype = ctypes.c_int
    except Exception as e:
        raise RuntimeError(f"Worker Init Failed: {e}")

    shared_salt = (ctypes.c_ubyte * 8)(*salt_raw)
    shared_cipher_len = len(cipher_raw)
    shared_cipher = (ctypes.c_ubyte * shared_cipher_len)(*cipher_raw)

def worker_batch_task(task_data):
    """
    Mengerjakan SEJUMLAH password (Batch).
    """
    batch_tuples, all_words = task_data
    
    checked = 0
    
    for p_tuple in batch_tuples:
        # Gabungkan tuple menjadi string password
        password_str = "".join(p_tuple)
        pass_c = password_str.encode('utf-8')
        
        # Cek ke Go
        match = shared_lib.CheckPassword(pass_c, shared_salt, shared_cipher, shared_cipher_len)
        checked += 1
        
        if match == 1:
            return (True, password_str, checked)
            
    # Lapor balik jumlah yang sudah dicek
    return (False, None, checked)

def chunked_iterable(iterable, size):
    """Helper untuk memotong generator menjadi batch kecil"""
    it = iter(iterable)
    while True:
        chunk = tuple(itertools.islice(it, size))
        if not chunk:
            break
        yield chunk

def format_time(seconds):
    if seconds < 60: return f"{seconds:.1f}s"
    if seconds < 3600: return f"{seconds/60:.1f}m"
    if seconds < 86400: return f"{seconds/3600:.1f}h"
    return f"{seconds/86400:.1f} days"

# ==============================================================================
# MAIN SYSTEM
# ==============================================================================
def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*60)
    print("   🚀 DIAMOND SOLVER - STABLE EDITION (100% CPU)")
    print("="*60)

    # 1. LOAD FILES
    if not os.path.exists(LIB_PATH): print(f"[FATAL] {LIB_PATH} missing"); return
    if not os.path.exists(KEYS_FILE): print(f"[FATAL] {KEYS_FILE} missing"); return

    try:
        with open(MESSAGE_FILE, "r") as f:
            raw = base64.b64decode(f.read().strip())
        salt_bytes = raw[8:16]
        cipher_bytes = raw[16:]
    except Exception as e:
        print(f"[FATAL] Message corrupt: {e}"); return

    with open(KEYS_FILE, "r") as f:
        words = [line.strip() for line in f if line.strip()]
    
    n_words = len(words)
    total_combinations = math.factorial(n_words)

    print(f"[INPUT] {n_words} Kata -> {total_combinations:,} Kombinasi")
    
    # 2. TASK GENERATOR (BATCHED)
    perms_gen = itertools.permutations(words)
    tasks = ((chunk, words) for chunk in chunked_iterable(perms_gen, BATCH_SIZE))

    # 3. WORKER SETUP (Murni 1 Core = 1 Worker)
    # Tidak ada lagi pengalian dengan 1.5
    total_workers = multiprocessing.cpu_count()
    
    print("-" * 60)
    print(f"[ENGINE] Workers : {total_workers} (100% Physical Cores)")
    print(f"[ENGINE] Batch   : {BATCH_SIZE} password/update")
    print("-" * 60)
    time.sleep(1)

    # 4. EXECUTION
    start_time = time.time()
    total_checked = 0
    session_start = time.time()

    with multiprocessing.Pool(processes=total_workers, initializer=init_worker, initargs=(salt_bytes, cipher_bytes)) as pool:
        
        # Gunakan imap_unordered
        result_iterator = pool.imap_unordered(worker_batch_task, tasks)
        
        while True:
            try:
                # --- UPDATE DASHBOARD ---
                elapsed = time.time() - session_start
                if elapsed < 0.1: elapsed = 0.1
                
                speed = total_checked / elapsed
                
                # CPU Monitor
                cpu_usage = psutil.cpu_percent(interval=None) if PSUTIL_AVAIL else 0.0

                remaining = total_combinations - total_checked
                eta_seconds = remaining / speed if speed > 0 else 0
                
                percent = (total_checked / total_combinations) * 100 if total_combinations > 0 else 0
                
                # Format Speed
                if speed < 1000:
                    speed_str = f"{speed:.1f} H/s"
                else:
                    speed_str = f"{speed/1000:.1f} k/s"

                # TAMPILAN
                sys.stdout.write(f"\rCPU:{cpu_usage:4.1f}% | Prog:{percent:6.4f}% | Spd: {speed_str} | ETA: {format_time(eta_seconds)} | Chk: {total_checked:,}   ")
                sys.stdout.flush()

                # --- BLOCKING WAIT ---
                res = next(result_iterator) 
                
                is_found, pw, count = res
                
                total_checked += count
                
                if is_found:
                    print(f"\n\n[🔥 MATCH FOUND 🔥] {pw}")
                    with open(FILE_LOG_SUCCESS, "w") as f: f.write(pw)
                    pool.terminate()
                    break

            except StopIteration:
                break
            except KeyboardInterrupt:
                pool.terminate()
                print("\n[STOP]"); return
            except Exception as e:
                pool.terminate()
                print(f"\n[ERROR] {e}"); return

    print("\n" + "="*60)
    print("SELESAI.")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
