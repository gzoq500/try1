import itertools
import ctypes
import os
import sys
import time
import base64
import multiprocessing
import json
import math

# ==============================================================================
# ⚙️ REALISTIC CONFIGURATION
# ==============================================================================
LIB_PATH = "./solver_lib.so"
KEYS_FILE = "keys-input.txt"
MESSAGE_FILE = "message.b64"
FILE_LOG_SUCCESS = "found.log"
FILE_CHECKPOINT = "checkpoint.json"

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
        shared_lib.CheckPassword.argtypes = [
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int
        ]
        shared_lib.CheckPassword.restype = ctypes.c_int
    except Exception as e:
        # Critical failure, raise to parent
        raise RuntimeError(f"Worker Init Failed: {e}")

    shared_salt = (ctypes.c_ubyte * 8)(*salt_raw)
    shared_cipher_len = len(cipher_raw)
    shared_cipher = (ctypes.c_ubyte * shared_cipher_len)(*cipher_raw)

def worker_task(task_data):
    """
    Mengerjakan 1 Blok (Dimulai dengan kata tertentu).
    Tidak ada disk I/O untuk log gagal. Murni CPU.
    """
    start_word, all_words, r = task_data
    
    # Siapkan list kata sisa
    remaining_words = list(all_words)
    remaining_words.remove(start_word)
    
    local_count = 0
    
    # Loop Permutasi (Heavy CPU Loop)
    for p in itertools.permutations(remaining_words, r - 1):
        # String concatenation di Python cukup cepat untuk short strings
        password_str = start_word + "".join(p)
        pass_c = password_str.encode('utf-8')
        
        # Panggil C Function (Zero overhead memory copy karena pointer)
        match = shared_lib.CheckPassword(pass_c, shared_salt, shared_cipher, shared_cipher_len)
        local_count += 1
        
        if match == 1:
            return (True, password_str, local_count, start_word)
            
        # Optional: Update status internal worker (bisa di-skip demi speed)
    
    return (False, None, local_count, start_word)

def format_time(seconds):
    """Helper untuk format waktu manusiawi"""
    if seconds < 60: return f"{seconds:.1f}s"
    if seconds < 3600: return f"{seconds/60:.1f}m"
    if seconds < 86400: return f"{seconds/3600:.1f}h"
    if seconds < 31536000: return f"{seconds/86400:.1f} days"
    return f"{seconds/31536000:.1f} YEARS"

# ==============================================================================
# MAIN SYSTEM
# ==============================================================================
def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("="*60)
    print("   🚀 DIAMOND SOLVER - LEAN & REALISTIC VERSION")
    print("="*60)

    # 1. VALIDASI FILE
    if not os.path.exists(LIB_PATH):
        print(f"[FATAL] {LIB_PATH} missing. Compile Go dulu!"); return
    if not os.path.exists(KEYS_FILE):
        print(f"[FATAL] {KEYS_FILE} missing."); return

    # 2. LOAD DATA
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

    # 3. REALITY CHECK (SANGAT PENTING)
    print(f"[INPUT] {n_words} Kata Unik")
    print(f"[SCOPE] {total_combinations:,} Kombinasi Total (N!)")
    
    # Asumsi speed single core Go AES modern ~2-5 Juta/detik
    # Total system speed estimasi (misal 8 core) ~ 20 Juta/detik
    # Batas wajar brute force modern per hari ~ 1 Triliun hash (optimis)
    
    if n_words >= 14:
        print("\n[⚠️ PERINGATAN LOGIKA ⚠️]")
        print(f"Jumlah kombinasi {n_words}! sangat besar.")
        print("Secara matematis, ini mungkin butuh waktu BERTAHUN-TAHUN.")
        print("Lanjutkan hanya jika Anda yakin password tidak menggunakan semua kata.")
        input("Tekan ENTER untuk nekat lanjut, atau Ctrl+C untuk batal...")

    # 4. CHECKPOINT SYSTEM
    completed_blocks = []
    if os.path.exists(FILE_CHECKPOINT):
        try:
            with open(FILE_CHECKPOINT, "r") as f:
                completed_blocks = json.load(f)
            print(f"[RESUME] Melanjutkan dari {len(completed_blocks)}/{n_words} blok tersimpan.")
        except:
            print("[WARN] Checkpoint corrupt, reset ulang.")
            completed_blocks = []

    # 5. TASK GENERATION
    tasks = []
    for w in words:
        if w in completed_blocks: continue
        tasks.append((w, words, n_words))

    if not tasks:
        print("[INFO] Semua tugas sudah selesai menurut checkpoint.")
        return

    # 6. WORKER SETUP (NO OVERDRIVE)
    # Gunakan jumlah core fisik asli. Overcommit hanya menambah latency.
    total_workers = multiprocessing.cpu_count()
    
    print("-" * 60)
    print(f"[ENGINE] CPU Cores : {total_workers}")
    print(f"[ENGINE] I/O Logging : DISABLED (Demi Speed)")
    print("-" * 60)
    time.sleep(1)

    # 7. EXECUTION LOOP
    start_time = time.time()
    
    # Hitung base progress dari checkpoint
    perms_per_block = math.factorial(n_words - 1)
    total_checked = len(completed_blocks) * perms_per_block
    
    # Session metrics
    session_checked = 0
    session_start = time.time()

    with multiprocessing.Pool(processes=total_workers, initializer=init_worker, initargs=(salt_bytes, cipher_bytes)) as pool:
        
        # Gunakan imap_unordered agar responsif
        result_iterator = pool.imap_unordered(worker_task, tasks)
        
        while True:
            try:
                # Update Dashboard (Non-blocking visual update)
                elapsed = time.time() - session_start
                if elapsed < 1: elapsed = 1
                
                speed = session_checked / elapsed
                
                # Estimasi Sisa Waktu (ETA)
                remaining_combs = total_combinations - total_checked
                eta_seconds = remaining_combs / speed if speed > 0 else 0
                eta_str = format_time(eta_seconds)

                # Format Angka
                percent = (total_checked / total_combinations) * 100
                speed_str = f"{speed/1_000_000:.2f}M/s" # Tampilkan dalam Juta/detik
                
                # Simple clean bar
                sys.stdout.write(f"\rProg: {percent:5.2f}% | Spd: {speed_str} | ETA: {eta_str} | Chk: {total_checked:,}   ")
                sys.stdout.flush()

                # BLOCKING CALL - Menunggu 1 worker selesai mengerjakan 1 blok
                # Kita tidak pakai timeout agar efisien CPU, update visual hanya terjadi
                # setiap kali ada blok yang selesai (atau bisa pakai thread terpisah u/ visual, tapi ini simpler)
                
                res = next(result_iterator) # <--- Critical Fix Python 3
                
                is_found, pw, count, finished_word = res
                
                total_checked += count
                session_checked += count
                
                if is_found:
                    print(f"\n\n[🔥 MATCH FOUND 🔥] {pw}")
                    with open(FILE_LOG_SUCCESS, "w") as f:
                        f.write(pw)
                    pool.terminate()
                    break
                
                # Save Checkpoint (Hanya start_word)
                completed_blocks.append(finished_word)
                with open(FILE_CHECKPOINT, "w") as f:
                    json.dump(completed_blocks, f)

            except StopIteration:
                break
            except KeyboardInterrupt:
                pool.terminate()
                print("\n\n[STOP] Dihentikan user.")
                return
            except Exception as e:
                print(f"\n[ERROR] {e}")
                pool.terminate()
                return

    print("\n" + "="*60)
    print("PENCARIAN SELESAI.")
    if not os.path.exists(FILE_LOG_SUCCESS):
        print("❌ Password tidak ditemukan di seluruh kombinasi.")
    print("="*60)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
