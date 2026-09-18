# main.py
from extract_afc_V1 import extrair_afd_relogio
from cloud import enviar_afd_para_servidor

def pipeline_principal():
    print("=== INICIANDO PIPELINE DE PONTO ELETRÔNICO (V1) ===")
    
    try:
        # Passo 1: Extrai o AFD do relógio Henry e obtém o caminho do arquivo gerado
        caminho_afd = extrair_afd_relogio()
        
        if caminho_afd and os.path.exists(caminho_afd):
            # Passo 2: Envia o arquivo obtido para o servidor PHP via cloud.py
            enviar_afd_para_servidor(caminho_afd)
            print("=== UNIDADE V1 PROCESSADA E ATUALIZADA! ===")
        else:
            print("Erro: Nenhum arquivo AFD válido foi gerado para envio.")
            
    except Exception as e:
        print(f"Falha crítica no pipeline: {e}")

if __name__ == "__main__":
    pipeline_principal()