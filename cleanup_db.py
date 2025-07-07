import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Carrega as variáveis de ambiente (como a DATABASE_URL) do arquivo .env
load_dotenv()

# Pega a URL do banco de dados
db_url = os.getenv('DATABASE_URL')
if not db_url:
    raise ValueError("DATABASE_URL não foi encontrada no seu ambiente. Verifique o arquivo .env")

# Corrige o prefixo para o SQLAlchemy, caso necessário
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

print("Conectando ao banco de dados...")

try:
    # Cria uma conexão com o banco de dados
    engine = create_engine(db_url)
    with engine.connect() as connection:
        # O comando SQL para apagar a tabela.
        # "IF EXISTS" garante que não dará erro se a tabela já tiver sido apagada.
        sql_command = text("DROP TABLE IF EXISTS alembic_version;")
        
        print("Executando comando para apagar a tabela 'alembic_version'...")
        connection.execute(sql_command)
        # Confirma a transação
        connection.commit()
        
    print("\n[SUCESSO] A tabela 'alembic_version' foi apagada com sucesso!")

except Exception as e:
    print(f"\n[ERRO] Ocorreu um erro ao tentar apagar a tabela: {e}")