<div align="center">

# 🧾 mcp-proof

### Livrez un serveur MCP avec un « reçu ».

**Auditez un serveur MCP au niveau du wire. Obtenez des preuves de conformité, de sécurité, de régression — et d'effets — dans un seul rapport de livraison reproductible et vérifiable hors ligne.**

`stdio + Streamable HTTP · générations 2026-07-28 et legacy · HTML / JSON / JUnit / SARIF`

[![ci](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml/badge.svg)](https://github.com/YuCPbit/mcp-proof/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)
[![checks](https://img.shields.io/badge/checks-32_modern_·_27_legacy_·_6_security_·_4_effect-6a5acd)](src/mcpproof/checks/)
[![transports](https://img.shields.io/badge/transports-stdio_·_HTTP-informational)](src/mcpproof/client_http.py)
[![license](https://img.shields.io/badge/license-MIT-black)](LICENSE)

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · **Français**

<a href="https://yucpbit.github.io/mcp-proof/report-filesystem.html"><img src="demo/report-filesystem.png" width="760" alt="Rapport de livraison mcp-proof pour le serveur filesystem officiel MCP — SHIP-READY, 11/11 contrôles MUST, table de conformité MSSS complète, 34/34 replays propres"></a>

**[Voir les rapports en ligne →](https://yucpbit.github.io/mcp-proof/)** · **[Évaluation effect-aware →](https://yucpbit.github.io/mcp-proof/evaluation/)**

*Un audit réel du serveur filesystem officiel MCP : 27 contrôles de conformité, la table MSSS, 34 replays de régression — ship-ready, une remarque consultative.*

</div>

---

## 🚀 Démarrage rapide

```bash
pip install git+https://github.com/YuCPbit/mcp-proof
mcp-proof run python my_server.py --fixtures fixtures/ --record-if-missing --out report.html
```

Pour auditer un serveur HTTP en cours d'exécution : `mcp-proof run --url http://localhost:8000/mcp --out report.html`

Les codes de sortie font office de garde-fou : **`0`** — tous les contrôles MUST passent, aucune découverte de sécurité bloquante, aucune dérive comportementale. **`1`** — l'audit s'est achevé et le serveur a échoué. **`2`** — l'audit ne s'est pas achevé et ne prouve rien sur le serveur, dans aucun sens.

```bash
mcp-proof plan python my_server.py                             # ce que l'auto-baseline appellerait, et pourquoi
mcp-proof record python my_server.py --fixtures fixtures/      # geler le contrat comportemental
mcp-proof replay --fixtures fixtures/ -- python my_server.py   # échec à la moindre dérive
mcp-proof inspect python my_server.py --out baseline.json      # geler la surface contractuelle
mcp-proof diff baseline.json current.json                      # BREAKING / ADDITIVE / METADATA, exit 1 si breaking
mcp-proof verify report.json                                   # revérifier hors ligne les empreintes du rapport
mcp-proof effects --sqlite state.db -- python my_server.py     # effets déclarés vs effets externes observés (v0.8)
```

Voyez la différence en 60 secondes avec la paire de démos intégrée — un serveur propre et un serveur avec neuf violations plantées :

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → 5 échecs MUST, 3 découvertes de sécurité
```

## 🔬 Les quatre volets

| Volet | Question posée | Méthode |
|---|---|---|
| **Conformité protocolaire** | Le serveur implémente-t-il MCP correctement sur le wire ? | Une sonde JSON-RPC artisanale observe le flux d'octets brut — négociation de génération, sémantique d'erreurs, les trois surfaces, pagination, hygiène stdout, sondes négatives vérifiées |
| **Sécurité et hygiène** | Les métadonnées d'outils exposées sont-elles propres ? | Analyse statique déterministe — instructions injectées, Unicode invisible, secrets divulgués, surfaces d'exécution non contraintes — chaque découverte reliée à un contrôle MSSS |
| **Régression comportementale** | Le serveur fait-il encore exactement ce qu'il faisait à la livraison ? | Enregistrement/replay de fixtures dorées empreintées SHA-256 derrière une porte d'intégrité fail-closed, dérive graduée par sévérité |
| **Conformité d'effets** (v0.8, recherche) | L'effet d'un outil sur le monde correspond-il à sa déclaration ? | Un observateur hors bande diffe l'état externe autour de chaque appel ; une sonde exerce les objets créés — voir [l'évaluation](https://yucpbit.github.io/mcp-proof/evaluation/) |

Tous les volets alimentent un seul rapport, qui se termine par une liste de corrections priorisée — un plan de remédiation prêt à l'emploi.

## ✨ Sous le capot

- **Contrôles au niveau du wire, chaque surface, chaque page, les deux générations.** 32 contrôles de la génération moderne (2026-07-28 : `server/discover`, enveloppe `_meta`, `resultType`, `ttlMs`/`cacheScope`, `-32022`, en-têtes de routage) et 27 de la génération legacy ; un collecteur de pagination unique alimente tous les volets, si bien qu'une violation en page 2 est auditée exactement comme en page 1.
- **Sondes négatives vérifiées.** TOOL-07 envoie des entrées qui violent *démontrablement* le schéma déclaré (une baseline valide dont exactement un champ est muté, les deux moitiés prouvées avec `jsonschema`) ; un serveur qui y répond normalement est signalé, et un blocage constitue sa propre découverte — jamais compté comme un rejet.
- **Contrôles de sécurité adossés à un standard public.** Six analyses déterministes sur chaque outil exposé, avec un parcoureur de schémas qui traverse `$ref`/`allOf`/imbrication — reliées à la matrice de 24 contrôles du [MCP Server Security Standard](https://mcp-security-standard.org), dont les verdicts ne dépassent jamais les preuves : **met** / **partial** / **gap** / **manual review**.
- **Une suite de régression qui se vérifie elle-même avant de juger quiconque.** Les fixtures portent un SHA-256 par contrat et une empreinte de manifeste sensible à l'ordre ; falsification, suppression, duplication — ou retrait du hash lui-même — interrompent le replay. Tout changement de valeur structurée/JSON vaut au moins une dérive `VALUE` ; `"approved"→"denied"` ne peut jamais passer pour cosmétique.
- **Deux empreintes honnêtement séparées.** `behavior_sha256` ne couvre que le comportement du serveur (reproductible entre machines) ; `run_hash` scelle le document entier par soustraction. `mcp-proof verify` revérifie les deux hors ligne — une preuve de cohérence interne, pas une signature.
- **Planification d'appels conservatrice.** L'auto-baseline saute les outils d'apparence mutante ; depuis la v0.8, les annotations MCP ne peuvent qu'*ajouter* de la prudence — un `readOnlyHint` non vérifié ne rend plus un outil auto-appelable, conformément à la position de la spec : « les annotations ne sont pas fiables ».
- **Un diff contractuel pour la CI.** `inspect` gèle la surface servie entièrement paginée dans un manifeste empreinté (et refuse de geler une demi-surface) ; `diff` classe `BREAKING` / `ADDITIVE` / `METADATA` — resserrement de schéma, rétrécissement d'enum, bascule optionnel→requis et affaiblissement des annotations de sécurité comptent tous comme breaking.
- **Reproductible par conception.** Zéro appel LLM, zéro clé d'API, synthèse d'arguments déterministe ; un comportement serveur identique reproduit des empreintes identiques sur toute machine.

## 🧪 Le volet de recherche effect-aware (v0.8)

La conformité protocolaire demande si le serveur *parle* MCP correctement. Le volet effets demande si **l'effet d'un outil sur le monde** correspond à sa déclaration — en lisant l'état externe hors bande (jamais la réponse de l'outil) et en **exerçant** les objets créés plutôt qu'en se fiant aux noms ou à la persistance.

```bash
python experiments/run_all.py         # E1–E3 depuis un état propre → experiments/results/index.html
python experiments/make_report.py     # rapports de preuves d'effets
```

Mesuré sur un banc d'essai synthétique contrôlé avec vérité terrain hors bande (performance de détection sur des incohérences plantées — **pas** une prévalence en production) :

| Propriété | Sonde / observation d'effets | Meilleure baseline |
|---|---|---|
| Détection de mensonges d'annotation (dont 3 invisibles dans la réponse) | precision / recall **1.000 / 1.000** | 1.000 / 0.333 |
| Authority-bearing vs simplement persistant | exactitude **1.000** | 0.875 (nom) · 0.625 (persistance) |
| Effectif vs simplement encore listé, après événements de cycle de vie | exactitude **1.000**, 0 autorité résiduelle manquée | 0.500 · 0.333, 1 manquée |

Deux découvertes invisibles pour un auditeur ordinaire : un outil `readOnlyHint: true` qui frappe silencieusement une clé d'API est attrapé par le diff d'état alors que sa réponse ressemble à une lecture normale ; et une clé d'API reste **effective après la révocation du grant qui l'a autorisée** — l'autorité résiduelle est mesurée par une sonde d'exercice, pas supposée du fait que l'objet existe encore.

Méthodologie complète, oracle, baselines et limites : [docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) · résultats en ligne : [site d'évaluation](https://yucpbit.github.io/mcp-proof/evaluation/).

## ✅ Validation

- **151 tests**, dont une suite adverse qui attaque l'auditeur lui-même : violations cachées en page 2, fixtures et manifestes falsifiés, downgrades par retrait de hash, verdicts de rapport édités — plus la suite adverse propre au volet effets (un mensonge invisible dans la réponse n'est attrapé que hors bande, persistance ≠ autorité, pas de sonde → `unknown` → SKIP).
- **CI sur Linux, macOS, Windows × Python 3.11–3.13**, plus un job d'empaquetage en installation fraîche qui audite un vrai serveur de bout en bout.
- **Validation croisée avec le SDK officiel v2 dans les deux sens** (`scripts/crosscheck_modern_server.py`).
- **Fail-closed partout** : tout ce que l'audit ne peut prouver se termine par exit `2` et une ligne stable — jamais de traceback, jamais d'audit silencieusement réduit, jamais de preuve à charge contre la cible.

## 📊 Audits réels, rapports réels

| Cible | Verdict | Rapport |
|---|---|---|
| **Serveur filesystem officiel** | ✅ SHIP-READY — 11/11 MUST, 34/34 replays propres, 4 outils d'écriture auto-sautés | [En ligne](https://yucpbit.github.io/mcp-proof/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **Serveur « everything » officiel** | ✅ SHIP-READY — 20/20 MUST + 7/7 SHOULD, 0 découverte de sécurité sur 13 outils (enregistrement volontairement sauté : son outil `get-env` déverse les variables d'environnement) | [En ligne](https://yucpbit.github.io/mcp-proof/report-everything.html) |
| **Serveur memory officiel** | ✅ SHIP-READY — 16/16 MUST, 4/4 replays, une remarque (requête `search_nodes.query` non contrainte) | [En ligne](https://yucpbit.github.io/mcp-proof/report-memory.html) |
| **Serveur sequential-thinking officiel** | ✅ SHIP-READY — 11/11 MUST ; l'enquête sur son SKIP honnête de TOOL-08 a révélé un inputSchema servi omettant un champ requis à l'exécution | [En ligne](https://yucpbit.github.io/mcp-proof/report-sequential-thinking.html) |
| **Serveur de génération 2026-07-28** (sans dépendance, validé contre le SDK) | ✅ SHIP-READY — génération auto-détectée, 23/23 MUST incl. sondes négatives | [En ligne](https://yucpbit.github.io/mcp-proof/report-modern.html) |
| Serveur de démo avec **9 violations plantées** | ❌ NOT SHIP-READY — 5 échecs MUST + 5 découvertes de sécurité, chacune attrapée avec preuve | [En ligne](https://yucpbit.github.io/mcp-proof/report-bad.html) |
| **Banc d'essai d'effets, variante `silent-keymint`** | ❌ EFF-01 FAIL — un outil annoté lecture seule frappe une clé d'API ; attrapé hors bande | [Preuves d'effets](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-silent-keymint.html) |

## 🧭 Rapport à la suite de conformité officielle

Le projet MCP maintient [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance) — des tests de scénarios du comportement protocolaire, y compris les flux d'authentification. Utilisez-la pour prouver le protocole. mcp-proof existe pour l'autre moitié : la **preuve de livraison** — un rapport empreinté et vérifiable hors ligne que le client peut conserver, la correspondance MSSS, la régression comportementale fail-closed, le diff contractuel comme porte de CI, les artefacts SARIF/JUnit, et le volet de recherche sur la conformité d'effets. Les deux se composent.

## 📡 Support protocolaire

| | |
|---|---|
| Transports | stdio ✅ · Streamable HTTP ✅ |
| Surfaces | tools ✅ · resources ✅ · prompts ✅ — sensibles aux capabilities dans les deux sens |
| Génération moderne `2026-07-28` (`server/discover`, `_meta` sans état) | ✅ auto-détectée — `--era auto\|modern\|legacy` |
| Génération legacy (handshake initialize, `2024-11-05` → `2025-11-25`) | ✅ tous les volets |
| Volet régression | ✅ les deux générations — session SDK (legacy) · session sonde (moderne) |

Fonctionne avec des serveurs écrits dans **n'importe quel langage** — mcp-proof parle au processus (ou à l'URL), pas à votre base de code.

## ⚙️ CI en une étape

```yaml
- uses: YuCPbit/mcp-proof@v0.8.0
  with:
    server-command: python my_server.py
    fixtures: fixtures/
```

Le job échoue tant que le serveur n'est pas ship-ready, et laisse `mcp-proof-report.html` / `.json` / `.junit.xml` / `.sarif` à téléverser.

## 🏗️ Partir du gabarit propre à l'audit

Vous construisez un serveur plutôt que vous n'en auditez un ? [`templates/server-starter/`](templates/server-starter/) passe cet audit d'emblée — chaque pratique est annotée de l'identifiant du contrôle qu'elle satisfait.

## 🗺️ Feuille de route

| | |
|---|---|
| **Actuel — v0.8.0** | Volet de recherche effect-aware : observation d'effets hors bande, classification d'autorité par sonde, mesure de l'autorité résiduelle (`mcp-proof effects`, [`experiments/`](experiments/), [docs](docs/effect-aware-conformance.md)) ; correction de la confiance aux annotations ; [site d'évaluation](https://yucpbit.github.io/mcp-proof/evaluation/) repensé |
| **v0.7.2** | Correctif de véracité : empreintes du document entier, le retrait du hash d'une fixture vaut falsification, taxonomie unique des codes de sortie |
| **Ensuite** | Approfondissement 2026-07-28 (allers-retours MRTR `input_required`) · validation croisée avec la suite officielle en CI · un adaptateur d'observation d'effets pour fournisseur réel |
| **Plus tard** | Lots de preuves signés (attestation) · volet sémantique opt-in — en attente jusqu'à l'achèvement du cœur déterministe |

L'historique des versions vit dans [CHANGELOG.md](CHANGELOG.md).

## 🔍 Limites

mcp-proof prouve ce qui peut l'être de façon déterministe, et dit lequel est lequel :

- Les contrôles de sécurité couvrent la surface protocolaire et métadonnées observable ; les contrôles MSSS exigeant des preuves de déploiement, de source ou de processus restent toujours en **manual review** — jamais supposés satisfaits.
- **Les flux d'autorisation sont hors périmètre** du rapport de livraison (la suite officielle couvre les scénarios d'auth). Le volet effets raisonne sur des *objets* porteurs d'autorité, sur un banc d'essai contrôlé — il n'audite pas un déploiement OAuth de production.
- **Le volet effets est un instrument de mesure, pas un volet boîte noire.** Il lui faut un canal d'observation (un store SQLite, un répertoire cloisonné) ; ce qu'il ne peut observer est rapporté `unknown`/SKIP, jamais supposé absent. Ses chiffres sont une performance de détection sur banc d'essai, pas une prévalence en production ([détails](docs/effect-aware-conformance.md)).
- L'auto-baseline utilise une heuristique de noms conservatrice ; depuis la v0.8, un `readOnlyHint` non vérifié ne la contourne plus. Relisez la liste des outils sautés avant de faire confiance à une baseline enregistrée contre la production.
- La justesse sémantique (la réponse *veut-elle dire* la bonne chose ?) est, par conception, hors du cœur déterministe.

## 📄 Licence

MIT — la taxonomie de la section de conformité MSSS suit le [MCP Server Security Standard](https://mcp-security-standard.org) (CC BY-SA 4.0).
