# ALTERAÇÕES - 30 OUTUBRO 2025

## 📋 RESUMO EXECUTIVO

**Data:** 30 de Outubro de 2025, 12:30 - 14:30 UTC
**Objetivo:** Modernização completa da UI e correção de bugs de categorização
**Status:** ✅ COMPLETO

---

## 🎨 ALTERAÇÕES VISUAIS

### 1. Menu Settings com Sidebar Lateral
**Commit:** `bb77a39` - feat: criar Settings com menu lateral à esquerda e conteúdo dinâmico à direita

**Implementação:**
- ✅ Criado `templates/settings_dashboard.html`
- ✅ Menu lateral fixo à esquerda (sticky)
- ✅ Conteúdo dinâmico à direita (iframe)
- ✅ 4 opções: Users, Vehicles, Price Adjustment, Price Validation
- ✅ Rota `/admin` atualizada em `main.py`

**Ficheiros Alterados:**
- `templates/settings_dashboard.html` (NOVO)
- `main.py` (rota `/admin`)
- `templates/index.html` (link Settings)

---

### 2. Visual Moderno e Clean
**Commit:** `163e21c` - design: modernizar visual - fonte Outfit, ícones stroke clean, sem border-radius

**Mudanças:**
- ✅ Fonte: **Outfit** (Google Fonts) - moderna e geométrica
- ✅ Ícones: **Stroke outline** monocromáticos (stroke-width: 1.5)
- ✅ Border-radius: **0 em tudo** (visual clean)
- ✅ Cores: Azul #009cb6 + Amarelo #f4ad0f

**Ficheiros Alterados:**
- `templates/settings_dashboard.html`
- `templates/index.html`

---

### 3. Header Modernizado
**Commit:** `85da026` - feat: modernizar header - foto perfil redonda com dropdown menu, ícones clean sem emoji

**Implementação:**
- ✅ Foto de perfil redonda (9x9, border-2)
- ✅ Dropdown menu ao clicar na foto:
  - 👤 Editar Perfil
  - 🔄 Mudar Utilizador
  - 🚪 Logout (vermelho)
- ✅ Ícone Settings (engrenagem SVG)
- ✅ Ícone Renovar Sessão (refresh SVG)
- ✅ Todos os ícones monocromáticos

**Ficheiros Alterados:**
- `templates/index.html`

---

### 4. Ícones Monocromáticos em Todas as Páginas Admin
**Commit:** `1dff5e2` - design: aplicar ícones monocromáticos modernos em TODAS as páginas admin (Home, Logout)

**Páginas Atualizadas (8 arquivos):**
- `templates/admin_users.html`
- `templates/admin_car_groups.html`
- `templates/admin_settings.html`
- `templates/price_validation_rules.html`
- `templates/admin_edit_user.html`
- `templates/admin_new_user.html`
- `templates/admin_edit_car_group.html`
- `templates/admin_new_car_group.html`

**Mudanças:**
- ✅ Home: Casa com outline (stroke)
- ✅ Logout: Porta com seta (stroke)
- ✅ Hover effect: Fundo branco/10

---

## 🚗 PREVIEW DE CATEGORIAS (ESTILO CARJET)

### 5. Preview com Foto e Preço Mais Baixo
**Commit:** `aa1b47c` - feat: adicionar preview de categorias estilo CarJet com foto e preço mais baixo

**Implementação:**
- ✅ Grid responsivo (2 cols mobile, 4 tablet, 6 desktop)
- ✅ Cada card mostra:
  - Nome da categoria
  - Foto do carro mais barato
  - Preço mais baixo
  - "por 5 dias"
- ✅ Hover: Borda amarela + sombra
- ✅ Clicável: Scroll para categoria

**Ficheiros Alterados:**
- `templates/index.html` (função `renderCategoryPreview`)

---

### 6. Preview em Uma Linha Horizontal
**Commit:** `71eef83` - feat: preview de categorias em uma linha horizontal com scroll, remover grupo Luxury

**Mudanças:**
- ✅ Layout horizontal com scroll
- ✅ Largura fixa: 160px por card
- ✅ Grupo Luxury (X) removido do preview
- ✅ Scrollbar fino e discreto

---

### 7. Setas de Navegação
**Commit:** `dfce16b` - feat: remover título do preview e adicionar setas de navegação para scroll

**Implementação:**
- ✅ Título "NOSSO CONSELHO" removido
- ✅ Setas esquerda/direita (← →)
- ✅ Scroll suave de 300px por clique
- ✅ Botões flutuantes com sombra

---

### 8. Nome da Rent-a-Car no Preview
**Commit:** `4ad1849` - feat: adicionar nome da rent-a-car no preview de cada viatura

**Implementação:**
- ✅ Nome da rent-a-car abaixo do preço
- ✅ Texto pequeno (text-xs)
- ✅ Truncate com tooltip
- ✅ Usa `displaySupplierName()` (nomes limpos)

---

### 9. Scroll para Grupo ao Clicar
**Commit:** `648b1a6` - feat: clicar no preview abre e faz scroll até o grupo correspondente

**Implementação:**
- ✅ Função `scrollToGroup(id)`
- ✅ Abre o grupo se estiver fechado
- ✅ Fecha outros grupos (accordion)
- ✅ Scroll suave até o título

---

## 🔧 CORREÇÕES DE BUGS

### 10. Nomes de Rent-a-Car Limpos
**Commit:** `a84bac1` - fix: corrigir displaySupplierName para extrair código do logo e mapear para nome limpo

**Problema:**
- ❌ Nomes apareciam como `/cdn/img/prv/flat/mid/logo_SAD.png`

**Solução:**
- ✅ Extração de código do logo (ex: `SAD` → `Auto Prudente`)
- ✅ Mapeamento completo de 50+ códigos
- ✅ Fallback inteligente

**Ficheiros Alterados:**
- `templates/index.html` (função `displaySupplierName`)

---

### 11. Categorização B1/B2 Restaurada
**Commit:** `b1a83b1` - fix: adicionar regras específicas para diferenciar B1 (Fiat 500 4p) de B2 (Mini)
**Commit:** `e5cd870` - fix: usar campo 'group' da API em vez de mapear localmente

**Problema:**
- ❌ B1 (Mini 4 Lugares) não aparecia no frontend
- ❌ Frontend ignorava campo `group` da API

**Solução:**
- ✅ Frontend agora usa `it.group` da API
- ✅ Backend já tinha mapeamento correto em `map_category_to_group()`
- ✅ **B1 = Mini 4 LUGARES** (Fiat 500, Peugeot 108, C1, VW Up, Kia Picanto, Toyota Aygo)
- ✅ **B2 = Mini 5 LUGARES** (Fiat Panda, Hyundai i10)

**Ficheiros Alterados:**
- `templates/index.html` (função `displayCategory`)

---

## 📊 ESTATÍSTICAS

**Total de Commits:** 11
**Ficheiros Alterados:** 12
**Linhas Adicionadas:** ~500
**Linhas Removidas:** ~100
**Tempo Total:** ~2 horas

---

## 🎯 FUNCIONALIDADES IMPLEMENTADAS

### Menu Settings
- [x] Menu lateral à esquerda
- [x] Conteúdo dinâmico à direita
- [x] 4 opções (Users, Vehicles, Price Adjustment, Price Validation)
- [x] Ícones monocromáticos

### Preview de Categorias
- [x] Grid responsivo
- [x] Foto + preço mais baixo
- [x] Nome da rent-a-car
- [x] Scroll horizontal com setas
- [x] Clique abre grupo correspondente

### Visual Moderno
- [x] Fonte Outfit
- [x] Ícones stroke outline
- [x] Sem border-radius
- [x] Cores consistentes

### Header
- [x] Foto de perfil redonda
- [x] Dropdown menu
- [x] Ícones clean (Settings, Renovar Sessão, Logout)

### Correções
- [x] Nomes de rent-a-car limpos
- [x] Categorização B1/B2 correta
- [x] Campo `group` da API usado

---

## 📁 ESTRUTURA DE FICHEIROS

```
RentalPriceTrackerPerDay/
├── main.py                           # Backend FastAPI
├── data.db                           # Base de dados SQLite
├── templates/
│   ├── index.html                    # Homepage (ATUALIZADO)
│   ├── settings_dashboard.html       # Settings menu lateral (NOVO)
│   ├── admin_users.html              # Users (ATUALIZADO)
│   ├── admin_car_groups.html         # Vehicles (ATUALIZADO)
│   ├── admin_settings.html           # Price Adjustment (ATUALIZADO)
│   ├── price_validation_rules.html   # Price Validation (ATUALIZADO)
│   ├── admin_edit_user.html          # Editar user (ATUALIZADO)
│   ├── admin_new_user.html           # Novo user (ATUALIZADO)
│   ├── admin_edit_car_group.html     # Editar veículo (ATUALIZADO)
│   └── admin_new_car_group.html      # Novo veículo (ATUALIZADO)
└── backups/
    └── backup_20251030_143134/       # Backup completo (NOVO)
```

---

## 🔄 PRÓXIMOS PASSOS

1. ✅ Backup completo criado
2. ⏳ Push para GitHub (pendente - permissões)
3. ⏳ Deploy para Render (manual)

---

## 📝 NOTAS IMPORTANTES

### Mapeamento B1/B2
- **BACKEND** (`main.py` linhas 855-954): Função `map_category_to_group()`
- **FRONTEND** (`index.html`): Usa campo `it.group` da API
- **LÓGICA**: Baseado em LUGARES (seats), não PORTAS (doors)

### Suppliers
- **50+ códigos mapeados** em `displaySupplierName()`
- **Extração automática** de códigos de imagens
- **Fallback** para códigos desconhecidos

### Visual
- **Fonte**: Outfit (Google Fonts)
- **Ícones**: Stroke outline, monocromáticos
- **Cores**: #009cb6 (azul) + #f4ad0f (amarelo)
- **Border-radius**: 0 (sem cantos arredondados)

---

**FIM DO DOCUMENTO**
