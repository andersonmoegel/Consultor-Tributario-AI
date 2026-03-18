import httpx
import uvicorn
import urllib3
from typing import List, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
from duckduckgo_search import DDGS  # Biblioteca estável para busca

# Desabilita avisos de certificados
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURAÇÃO ---
GROQ_API_KEY = "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" 
MODELO = "llama-3.3-70b-versatile"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cliente Groq com timeout estendido para processar o contexto da web
groq_client = Groq(
    api_key=GROQ_API_KEY,
    http_client=httpx.Client(verify=False, timeout=45.0)
)

class Mensagem(BaseModel):
    role: str
    content: str

class Req(BaseModel):
    pergunta: str
    historico: List[Mensagem] = []

def buscar_na_web(query: str) -> List[Dict]:
    """Realiza busca no DuckDuckGo de forma anônima e rápida."""
    resultados = []
    try:
        # Adicionamos termos técnicos para focar na legislação brasileira
        query_otimizada = f"{query} reforma tributária brasil lei 2025 2026"
        
        with DDGS() as ddgs:
            # region='br-pt' garante resultados do Brasil
            # max_results=3 para não estourar o limite de tokens da Groq
            search_results = ddgs.text(query_otimizada, region='br-pt', safesearch='off', max_results=3)
            
            for r in search_results:
                resultados.append({
                    "fonte": r['title'],
                    "url": r['href'],
                    "texto": r['body']
                })
    except Exception as e:
        print(f"Erro na busca DuckDuckGo: {e}")
    return resultados

@app.post("/perguntar")
async def responder(req: Req):
    # 1. Busca informações atualizadas
    dados_web = buscar_na_web(req.pergunta)
    
    # 2. Constrói o contexto para a IA
    if dados_web:
        contexto_corpo = "\n".join([f"FONTE: {d['fonte']}\nCONTEÚDO: {d['texto']}" for d in dados_web])
        contexto_web = f"### INFORMAÇÕES RECENTES DA WEB (PRIORIDADE):\n{contexto_corpo}\n"
    else:
        contexto_web = "Não foram encontrados dados recentes. Baseie-se na legislação vigente (EC 132/2023)."

    # 3. Estrutura de Mensagens (System Prompt Robusto)
    mensagens_ia = [
        {
            "role": "system", 
            "content": (
                "Você é um Consultor Fiscal de alto nível. "
                "Sua missão é explicar mudanças na Reforma Tributária de forma clara. "
                "Se o contexto da web trouxer datas ou alíquotas de 2025/2026, use-as. "
                "Mantenha as respostas em no máximo 3 parágrafos curtos."
            )
        }
    ]
    
    # Adiciona histórico (últimas 4 mensagens para manter memória)
    for msg in req.historico[-4:]:
        mensagens_ia.append({"role": msg.role, "content": msg.content})
    
    # Pergunta atual com o contexto injetado
    mensagens_ia.append({
        "role": "user", 
        "content": f"{contexto_web}\n\nPERGUNTA DO USUÁRIO: {req.pergunta}"
    })

    try:
        completion = groq_client.chat.completions.create(
            model=MODELO,
            messages=mensagens_ia,
            temperature=0.2, # Baixa para evitar alucinações jurídicas
            max_tokens=800
        )
        resposta = completion.choices[0].message.content
    except Exception as e:
        resposta = "Ocorreu um erro ao processar sua consulta na IA. Tente novamente em instantes."
        print(f"Erro Groq: {e}")

    # Define a fonte principal para o front-end
    fonte_final = "Legislação Consolidada"
    if dados_web:
        # Pega o domínio da primeira URL para ficar elegante
        link = dados_web[0]['url']
        fonte_final = f"{dados_web[0]['fonte']} ({link})"

    return {
        "resposta": resposta,
        "fonte": fonte_final
    }

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)