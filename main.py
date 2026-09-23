import os
from extract_afc_v1 import automatizar_download_afd_v1
from extract_afc_v2 import automatizar_download_afd_v2
from cloud import enviar_afd_para_servidor

def pipeline_principal():
    print("=== INICIANDO PIPELINE COMPLETO DE PONTO ELETRÔNICO (V1 & V2) ===")
    
    # --- 1. PROCESSAMENTO DA UNIDADE V1 ---
    print("\n--- [1/2] Processando Unidade V1 ---")
    try:
        caminho_afd_v1 = automatizar_download_afd_v1()
        
        if caminho_afd_v1 and os.path.exists(caminho_afd_v1):
            enviar_afd_para_servidor(caminho_afd_v1, unidade="V1")
            print("=== UNIDADE V1 PROCESSADA E ENVIADA COM SUCESSO! ===")
        else:
            print("Aviso: Nenhum arquivo AFD válido foi gerado para a V1.")
            
    except Exception as e:
        print(f"Falha crítica no pipeline da Unidade V1: {e}")

    # --- 2. PROCESSAMENTO DA UNIDADE V2 (Galpão Externo via Tailscale) ---
    print("\n--- [2/2] Processando Unidade V2 ---")
    try:
        caminho_afd_v2 = automatizar_download_afd_v2()
        
        if caminho_afd_v2 and os.path.exists(caminho_afd_v2):
            enviar_afd_para_servidor(caminho_afd_v2, unidade="V2")
            print("=== UNIDADE V2 PROCESSADA E ENVIADA COM SUCESSO! ===")
        else:
            print("Aviso: Nenhum arquivo AFD válido foi gerado para a V2.")
            
    except Exception as e:
        print(f"Falha crítica no pipeline da Unidade V2 (Verifique a conexão Tailscale/IP): {e}")

    print("\n=== PIPELINE DE COLETA E SINCRONIZAÇÃO FINALIZADO ===")

if __name__ == "__main__":
    pipeline_principal()