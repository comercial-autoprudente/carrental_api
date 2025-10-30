# INSTRUÇÕES DE RESTAURO - BACKUP 30 OUT 2025

## 📦 CONTEÚDO DO BACKUP

**Data:** 30 de Outubro de 2025, 14:31 UTC
**Localização:** `/Users/filipepacheco/CascadeProjects/RentalPriceTrackerPerDay/backups/backup_20251030_143134/`

### Ficheiros Incluídos:
- ✅ `data.db` - Base de dados SQLite completa
- ✅ `ALTERACOES_30_OUT_2025.md` - Documentação de todas as alterações
- ✅ `INSTRUCOES_RESTAURO.md` - Este ficheiro
- ✅ `git_log.txt` - Histórico completo de commits
- ✅ `git_diff.txt` - Diferenças desde último backup

---

## 🔄 COMO RESTAURAR

### 1. Restaurar Base de Dados

```bash
# Parar o servidor
# Ctrl+C no terminal onde uvicorn está rodando

# Fazer backup da DB atual (segurança)
cp data.db data.db.backup_antes_restauro

# Restaurar DB do backup
cp backups/backup_20251030_143134/data.db data.db

# Reiniciar servidor
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

### 2. Restaurar Código (Git)

```bash
# Ver commits disponíveis
git log --oneline -20

# Restaurar para commit específico
git checkout e5cd870  # Último commit do backup

# OU criar branch do backup
git checkout -b backup_30_out_2025 e5cd870

# Voltar para main
git checkout main
```

---

### 3. Restaurar Ficheiros Específicos

```bash
# Restaurar um ficheiro específico de um commit
git checkout e5cd870 -- templates/index.html

# Restaurar settings_dashboard.html
git checkout e5cd870 -- templates/settings_dashboard.html

# Restaurar main.py
git checkout e5cd870 -- main.py
```

---

## 📋 COMMITS INCLUÍDOS NO BACKUP

```
e5cd870 - fix: usar campo 'group' da API em vez de mapear localmente
b1a83b1 - fix: adicionar regras específicas para diferenciar B1/B2
648b1a6 - feat: clicar no preview abre e faz scroll até o grupo
4ad1849 - feat: adicionar nome da rent-a-car no preview
dfce16b - feat: remover título do preview e adicionar setas
a84bac1 - fix: corrigir displaySupplierName para extrair código do logo
71eef83 - feat: preview de categorias em uma linha horizontal
1dff5e2 - design: aplicar ícones monocromáticos em TODAS as páginas admin
aa1b47c - feat: adicionar preview de categorias estilo CarJet
85da026 - feat: modernizar header - foto perfil redonda com dropdown
163e21c - design: modernizar visual - fonte Outfit, ícones stroke clean
bb77a39 - feat: criar Settings com menu lateral à esquerda
```

---

## 🗄️ ESTRUTURA DA BASE DE DADOS

### Tabelas Principais:
- `users` - Utilizadores (admin, carlpac82, dprudente)
- `car_groups` - Grupos de veículos (B1, B2, D, E1, E2, F, G, J1, J2, L1, L2, M1, M2, N)
- `price_validation_rules` - Regras de validação de preços

### Dados Importantes:
- **Users:** 3 utilizadores ativos
- **Fotos de perfil:** `/uploads/profiles/carlpac82.PNG`, `/uploads/profiles/dprudente.JPG`
- **Veículos:** 15 grupos mapeados

---

## 🔧 VERIFICAÇÃO PÓS-RESTAURO

### 1. Verificar Base de Dados

```bash
# Abrir SQLite
sqlite3 data.db

# Verificar users
SELECT username, email, is_admin FROM users;

# Verificar grupos
SELECT DISTINCT code FROM car_groups ORDER BY code;

# Sair
.quit
```

### 2. Verificar Servidor

```bash
# Iniciar servidor
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Testar endpoints
curl http://localhost:8000/
curl http://localhost:8000/admin
```

### 3. Verificar Frontend

1. Abrir `http://localhost:8000`
2. Login: `admin` / `admin`
3. Verificar:
   - ✅ Preview de categorias (horizontal com setas)
   - ✅ Clique em Settings abre menu lateral
   - ✅ Foto de perfil redonda com dropdown
   - ✅ Ícones monocromáticos
   - ✅ Grupos B1 e B2 aparecem corretamente

---

## 📊 ESTADO DO SISTEMA

### Funcionalidades Ativas:
- ✅ Login/Logout
- ✅ Homepage com preview de categorias
- ✅ Settings com menu lateral
- ✅ Admin Users (CRUD)
- ✅ Admin Vehicles (CRUD)
- ✅ Price Adjustment
- ✅ Price Validation
- ✅ Scraping CarJet (Playwright)

### Configuração:
- **Servidor:** uvicorn (FastAPI)
- **Base de Dados:** SQLite (`data.db`)
- **Frontend:** Jinja2 templates + TailwindCSS
- **Scraping:** Playwright (Firefox, Webkit)

---

## 🚨 PROBLEMAS CONHECIDOS

### 1. Permissões GitHub
- ❌ Sem permissões para push em `comercial-autoprudente/carrental_api`
- ✅ Commits salvos localmente
- ⚠️ Push manual necessário

### 2. Render Deploy
- ⚠️ Deploy manual necessário
- ✅ Código pronto para deploy

---

## 📞 CONTACTOS

**Desenvolvedor:** Cascade AI
**Data:** 30 Outubro 2025
**Versão:** v3.0 - Modern UI

---

## 🔐 CREDENCIAIS

```
Username: admin
Password: admin (ou admin123)

Username: carlpac82
Email: carlpac82@hotmail.com

Username: dprudente
Email: comercial.autoprudente@gmail.com
```

---

## 📝 NOTAS FINAIS

Este backup contém:
- ✅ Base de dados completa
- ✅ Histórico de commits
- ✅ Documentação de alterações
- ✅ Instruções de restauro

**IMPORTANTE:** Guardar este backup em local seguro!

---

**FIM DO DOCUMENTO**
