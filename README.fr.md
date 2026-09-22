<div align="center">

# 🧾 mcp-proof

### Livrez un serveur MCP avec un « reçu ».

**Auditez un serveur MCP au niveau du wire. Obtenez des preuves de conformité, de sécurité, de régression — et d'effets — dans un seul rapport de livraison reproductible et vérifiable hors ligne.**

**v0.8 étend la conformité sous la frontière de la réponse — un outil peut déclarer `readOnlyHint: true`, renvoyer une réponse parfaitement ordinaire, et frapper malgré tout un credential qui survit au grant qui l'a autorisé.** Un observateur hors bande lit les effets externes réels ; une sonde exerce l'autorité que les outils créent. **[→ le volet de recherche](docs/effect-aware-conformance.md)**

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

Les codes de sortie font office de garde-fou : **`0`** — tous les contrôles MUST passent, aucune découverte de sécurité bloquante (des remarques peuvent rester), aucune dérive comportementale. **`1`** — l'audit s'est achevé et le serveur a échoué. **`2`** — l'audit ne s'est pas achevé (baseline manquante, erreur interne de l'auditeur) et ne prouve rien sur le serveur, dans aucun sens.

```bash
mcp-proof plan python my_server.py                             # ce que l'auto-baseline appellerait, et pourquoi
mcp-proof record python my_server.py --fixtures fixtures/      # geler le contrat comportemental
mcp-proof replay --fixtures fixtures/ -- python my_server.py   # échec à la moindre dérive
mcp-proof inspect python my_server.py --out baseline.json      # geler la surface contractuelle
mcp-proof diff baseline.json current.json                      # BREAKING / ADDITIVE / METADATA, exit 1 si breaking
mcp-proof verify report.json                                   # revérifier hors ligne les empreintes internes du rapport
mcp-proof effects --sqlite state.db -- python my_server.py     # effets déclarés vs effets externes observés (v0.8)
mcp-proof effects --fs-root data/ -- python my_server.py       # même volet, serveurs adossés à un répertoire
```

Voyez la différence en 60 secondes avec la paire de démos intégrée — un serveur propre et un serveur avec neuf violations plantées :

```bash
mcp-proof run python demo/good_server.py --fixtures demo/fixtures-good --out report-good.html   # → SHIP-READY
mcp-proof run python demo/bad_server.py --out report-bad.html                                    # → 5 échecs MUST, 3 découvertes de sécurité
```

## 🔬 Les quatre volets

| Volet | Ce qu'il prouve | Méthode |
|---|---|---|
| **Conformité protocolaire** | Le serveur implémente MCP correctement sur le wire — négociation de génération, sémantique d'erreurs JSON-RPC, surfaces tool/resource/prompt, schémas de sortie, cohérence des capabilities, pagination, hygiène stdout | Une sonde JSON-RPC artisanale observe le flux d'octets brut, rien n'est lissé par un SDK |
| **Sécurité et hygiène** | Les métadonnées d'outils sont propres : pas d'instructions injectées, d'Unicode invisible, de secrets divulgués ni de surfaces d'exécution non contraintes | Analyse statique déterministe, chaque découverte portant son identifiant de contrôle MSSS |
| **Régression comportementale** | Le serveur fait encore exactement ce qu'il faisait à la livraison | Enregistrement/replay de fixtures dorées à empreinte de provenance, dérive graduée par sévérité |
| **Conformité d'effets** (v0.8, volet de recherche) | L'effet observé d'un outil sur l'état externe correspond à ses annotations déclarées ; les objets créés sont classés par sondage, pas par leur nom | Un observateur hors bande prend des instantanés du store d'état du serveur autour de chaque appel ; une sonde exerce les objets créés — nécessite un canal d'observation (`--sqlite` / `--fs-root`), voir plus bas. Validé sur trois serveurs tiers, pas seulement sur notre propre banc d'essai |

Chaque volet alimente un seul rapport — qui se termine par une liste de corrections priorisée, donc sert aussi de plan de remédiation.

## ✅ Validation

Un outil d'audit doit mériter plus de confiance que ce qu'il audite. Derrière chaque version :

- **160 tests**, dont une suite adverse qui attaque l'auditeur lui-même : violations cachées en page 2 des listes paginées, fixtures et manifestes falsifiés, tentatives de downgrade par retrait de hash, rapports aux bannières de verdict éditées, classes de dérive qui passaient autrefois, baselines synthétisées invalides — et, pour le volet effets, sa propre suite adverse : un outil annoté lecture seule qui frappe un credential détectable uniquement hors bande ; un objet persistant qui ne doit pas être classé authority-bearing ; un audit sans sonde dont les verdicts d'autorité doivent dégrader en `unknown`/SKIP au lieu de passer ; et un appel create+delete qui ne doit pas cacher sa suppression derrière l'effet de tête.
- **CI sur Linux, macOS et Windows × Python 3.11 / 3.12 / 3.13**, plus un job d'empaquetage qui construit la wheel, l'installe dans un environnement vierge et lance un audit réel contre un vrai serveur avant toute publication — et un **job experiments qui rejoue E1–E3 de zéro et échoue si les sorties ne sont pas identiques à l'octet aux résultats committés** : la reproductibilité est imposée par la CI, pas seulement affirmée.
- **Exercé contre des serveurs que nous n'avons pas écrits** : trois audits d'étude de cas de serveurs MCP tiers publiés (deux serveurs de référence officiels et un serveur communautaire — trois types de stores, avec et sans annotations), preuves committées — voir la section du volet effets plus bas.
- **Validation croisée avec le SDK officiel v2 dans les deux sens** : le client officiel adopte le serveur de test moderne artisanal de mcp-proof via `server/discover`, et mcp-proof passe entièrement au vert contre des serveurs SDK v2 officiels sur les deux transports (`scripts/crosscheck_modern_server.py`).
- **Fail-closed par conception** : une pagination interrompue, une fixture falsifiée ou invérifiable, une baseline manquante ou une erreur interne de l'auditeur arrêtent chacune l'audit bruyamment — et chaque commande répond avec la même taxonomie : exit `2` et une ligne stable, jamais de traceback, jamais d'audit silencieusement réduit, jamais de preuve à charge contre la cible.
- **Rapports vérifiables hors ligne** : `mcp-proof verify report.json` recalcule les deux empreintes à partir des champs du rapport lui-même ; l'empreinte du document couvre tout ce qu'un lecteur voit — bannière de verdict, statut d'audit, compteurs, table MSSS, prochaines étapes — de sorte que toute édition postérieure la casse. C'est une preuve de cohérence interne, pas une signature (l'attestation est sur la feuille de route).

## ✨ Sous le capot

- 🔍 **Contrôles protocolaires au niveau du wire, chaque surface, chaque page, les deux générations** — mcp-proof parle JSON-RPC brut à votre serveur et détecte sa génération : 32 contrôles pour la génération moderne 2026-07-28 (`server/discover`, enveloppe `_meta` imposée, `resultType`, `ttlMs`/`cacheScope` sur chaque résultat cachable, rejet de version `-32022`, en-têtes de routage HTTP) et 27 pour la génération à handshake initialize — codes d'erreur exacts, validité des schémas, sortie structurée, hygiène stdout, sûreté de pagination sur les trois surfaces de liste, volets dédiés resources et prompts, et **sondes négatives vérifiées** : TOOL-07 envoie des entrées qui violent démontrablement l'inputSchema déclaré (une baseline valide dont exactement un champ est muté) et avertit quand le serveur y répond normalement — un blocage constitue sa propre découverte, jamais un rejet. Un collecteur de pagination unique alimente tous les volets : un outil caché en page 2 est audité exactement comme en page 1.
- 🛡️ **Audit de sécurité adossé à un standard public** — 6 contrôles déterministes (empoisonnement des descriptions d'outils, caractères invisibles/bidi, credentials divulgués, surfaces d'injection non contraintes, exécution shell affichée) sur chaque outil exposé de chaque page, avec un parcoureur de schémas qui traverse `$ref`/`allOf`/imbrication/éléments de tableaux — `config.shell.command` ne peut pas se cacher un niveau plus bas. Chaque contrôle correspond aux identifiants canoniques de la matrice de 24 contrôles du [MCP Server Security Standard](https://mcp-security-standard.org) (23 contrôles pleinement documentés plus l'emplacement du contrôle futur `MCP-DEPLOY-04`), rendue en table de conformité dont les verdicts ne dépassent jamais les preuves : preuve directe complète = **met**, preuve propre mais indirecte = **partial**, contrôle invisible aux checks = **manual review**.
- 🧪 **Des contrôles d'effets qui lisent le monde, pas la réponse (v0.8)** — avec un canal d'observation configuré (`--sqlite` pour un serveur adossé à SQLite, `--fs-root` pour un serveur adossé à un répertoire), le volet effets prend des instantanés de l'état externe avant et après chaque appel et les diffe en effets create/update/delete par objet, attribués à l'appel qui les a causés (ops par cible : un move ne peut pas cacher sa suppression derrière sa création). Quatre contrôles comparent cela aux annotations déclarées, en suivant exactement la sémantique de la spec — les défauts sont pessimistes, donc un hint *absent* n'est jamais signalé, seule une affirmation explicite falsifiée par l'effet observé l'est : EFF-01 (un outil `readOnlyHint: true` n'a causé aucune écriture observée), EFF-02 (aucune suppression observée sous un `destructiveHint: false` explicite), EFF-03 (l'appel répété à l'identique d'un outil `idempotentHint` est sans effet), EFF-06 (l'efficacité continue d'un credential créé dépend toujours du grant qui l'a autorisé — établi en révoquant chaque dépendance candidate hors bande, en ré-exerçant l'objet, puis en restaurant). Chaque champ de chaque enregistrement d'effet porte la manière dont il est connu — `declared`, `observed`, `probed` ou `unknown` — et une dimension sans canal SKIPpe au lieu de passer.
- 📼 **Une suite de régression que votre client conserve — et qui se vérifie avant de juger quiconque** — enregistre dans les deux générations ; les fixtures dorées gèlent le comportement du serveur avec une provenance SHA-256, tous types de contenu compris (les binaires en digests, une image substituée ne peut jamais rejouer OK). Avant tout replay, une porte d'intégrité recalcule chaque hash de contrat et l'empreinte du manifeste : une fixture manquante, falsifiée, dupliquée ou périmée interrompt le replay au lieu d'être silencieusement sautée — supprimer le hash stocké d'une fixture compte comme falsification, pas comme un ancien schéma, et les baselines antérieures au hachage de contrat sont refusées sauf opt-in explicite `--allow-legacy-fixtures`. Le replay gradue chaque dérive (`BREAKING` / `VALUE` / `COSMETIC` / `LATENCY`) — tout changement de valeur structurée/JSON vaut au moins `VALUE`, un `"approved"→"denied"` inversé ne peut jamais passer pour cosmétique — et préserve l'ordre des appels à état (fixtures numérotées, empreinte sensible à l'ordre). Une baseline n'est jamais créée implicitement : `run` échoue fermé quand les fixtures manquent, sauf opt-in `--record-if-missing`.
- 📄 **Un rapport pour les humains *et* les machines** — HTML autonome : navigation collante, ancres par contrôle (`report.html#SEC-03`), filtres attention/passed, carte de périmètre des preuves, matrice MSSS repliable ; `--pdf` pour l'impression. Le même modèle versionné sort en `--json` (schéma v3), `--junit` pour toute CI, `--sarif` pour l'onglet GitHub Security. Le volet effets rend sa propre page de preuves : annotations déclarées à côté de l'effet observé, la réponse qu'un auditeur limité aux réponses aurait lue, les objets produits, et le verdict autorité/dépendance de la sonde — chaque valeur étiquetée de sa manière d'être connue.
- 🔁 **Reproductible par conception** — zéro appel LLM, zéro clé d'API. Deux empreintes honnêtement séparées : `behavior_sha256` est calculée du seul comportement du serveur (verdicts de contrôles, verdicts de replay, faits protocolaires — jamais d'horodatages, de latence, de commande de lancement ni de version de l'auditeur), de sorte qu'un comportement identique s'empreinte identiquement sur toute machine ; `run_hash` gèle le document entier — preuves, bannière de verdict, statut, résumés, table MSSS — moins le seul bloc d'horodatage volatil. `mcp-proof verify` revérifie les deux hors ligne : une preuve de cohérence interne que toute édition postérieure casse, pas une signature. L'acceptation, c'est la vérification, pas la confiance.
- 🧯 **Planification d'appels conservatrice, et la correction de confiance v0.8** — l'auto-baseline classe les outils par une heuristique conservatrice de nom/description, et `mcp-proof plan` montre exactement ce qui serait appelé et sur quelle base avant que quoi que ce soit ne touche la production. Depuis la v0.8, les annotations MCP ne peuvent qu'*ajouter* de la prudence : `destructiveHint: true` force toujours le saut, mais un `readOnlyHint: true` non vérifié ne repêche plus un outil d'apparence mutante dans l'ensemble auto-appelable — la spec impose aux clients de traiter les annotations comme non fiables, et le volet effets existe précisément parce qu'un outil « lecture seule » peut frapper des credentials. `--include-destructive` et `--edge-cases` élargissent explicitement.
- 📋 **Un diff contractuel pour la CI** — `mcp-proof inspect` gèle la surface servie (capabilities + tools + resources + prompts, entièrement paginée, « absent » distinct de « vide ») dans un manifeste empreinté — et refuse d'en écrire un si une marche de pagination ne peut s'achever, car une demi-surface gelée comme « baseline » rend invisibles tous les diffs futurs contre la moitié manquante. Les métadonnées volatiles du wire sont retirées par position, jamais par nom de clé : une propriété de schéma utilisateur qui s'appelle par hasard `ttlMs` ou `nextCursor` reste contractuelle. `mcp-proof diff` classe chaque changement `BREAKING` / `ADDITIVE` / `METADATA` et sort non nul sur les breaking — resserrement de schéma, rétrécissement d'enum, bascules optionnel→requis, champs de sortie supprimés et annotations de sécurité affaiblies comptent tous.

## 📊 Audits réels, rapports réels

| Cible | Verdict | Rapport |
|---|---|---|
| **Serveur filesystem officiel** (`@modelcontextprotocol/server-filesystem`) | ✅ SHIP-READY — 11/11 MUST, 34/34 replays propres, 4 outils d'écriture auto-sautés | [En ligne](https://yucpbit.github.io/mcp-proof/report-filesystem.html) · [PDF](demo/report-filesystem.pdf) |
| **Serveur de référence « everything »** (`@modelcontextprotocol/server-everything`) | ✅ SHIP-READY — 20/20 MUST + 7/7 SHOULD, 0 découverte de sécurité sur 13 outils. Volets protocole + sécurité ; enregistrement volontairement sauté — son outil `get-env` déverse les variables d'environnement | [En ligne](https://yucpbit.github.io/mcp-proof/report-everything.html) |
| **Serveur memory officiel** (`@modelcontextprotocol/server-memory`) | ✅ SHIP-READY — 16/16 MUST, 4/4 replays propres, 5 outils write/delete auto-sautés, une remarque : `search_nodes.query` non contraint (SEC-04) | [En ligne](https://yucpbit.github.io/mcp-proof/report-memory.html) |
| **Serveur sequential-thinking officiel** (`@modelcontextprotocol/server-sequential-thinking`) | ✅ SHIP-READY — 11/11 MUST, 1/1 replay propre, une remarque (description d'outil de 2 781 caractères, SEC-05) ; l'enquête sur son SKIP honnête de TOOL-08 a révélé un inputSchema servi omettant un champ requis à l'exécution | [En ligne](https://yucpbit.github.io/mcp-proof/report-sequential-thinking.html) |
| **Serveur de génération 2026-07-28** (sans dépendance, validé croisé contre le SDK v2 officiel) | ✅ SHIP-READY — génération auto-détectée via `server/discover`, 23/23 MUST incl. sondes négatives, 2/2 replays | [En ligne](https://yucpbit.github.io/mcp-proof/report-modern.html) |
| Serveur de démo avec **9 violations plantées** | ❌ NOT SHIP-READY — 5 échecs MUST + 5 découvertes de sécurité (3 bloquantes, 2 consultatives), chacune attrapée avec preuve | [En ligne](https://yucpbit.github.io/mcp-proof/report-bad.html) |
| Serveur de démo bien élevé | ✅ SHIP-READY — 18/18 MUST, passage complet des trois volets, baseline de régression comprise | [En ligne](https://yucpbit.github.io/mcp-proof/report-good.html) |
| **Banc d'essai d'effets, variante `silent-keymint`** | ❌ EFF-01 FAIL — un outil annoté `readOnlyHint: true` renvoie une réponse de lecture normale tout en insérant une ligne dans `api_keys` ; le diff d'état hors bande attribue l'écriture à l'appel | [Preuves d'effets](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-silent-keymint.html) |
| **Étude de cas d'effets : serveur memory officiel** (store JSONL, entièrement annoté) | ✅ EFF-01/02/03 PASS — chaque déclaration readOnly, destructive et d'idempotence a tenu sous observation hors bande, y compris un `delete_entities` répété ; l'autorité SKIPpe honnêtement (pas de canal de sonde) | [Preuves d'effets](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-case-memory.html) |
| **Étude de cas d'effets : serveur filesystem officiel** (répertoire cloisonné, observateur standard) | ✅ EFF-01/02/03 PASS — 10 outils readOnly n'ont rien écrit ; la suppression observée de `move_file` est couverte par son `destructiveHint` — et cet appel a exposé (et corrigé) un angle mort d'EFF-02 limité à l'effet de tête | [Preuves d'effets](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-case-filesystem.html) |
| **Étude de cas d'effets : serveur SQLite communautaire** (`@executeautomation/database-server`, zéro annotation) | ✅ dégradation honnête — rien de déclaré, donc EFF-01/03 SKIP ; le `DELETE` observé est cohérent avec le défaut pessimiste de la spec ; les effets restent attribués ligne par ligne via le canal standard `--sqlite` | [Preuves d'effets](https://yucpbit.github.io/mcp-proof/evaluation/effect-report-case-sqlite.html) |

## 🧪 Le volet de recherche effect-aware (v0.8)

Les trois volets de livraison s'arrêtent au wire : leur notion de comportement est le flux d'octets des réponses. Le volet effets prolonge la même méthode déclaré-vs-observé un niveau plus bas. Ses pièces, concrètement :

- **Observateur** (`effects/observe.py`) : prend des instantanés de l'état externe — un store SQLite lu directement dans le fichier, ou une arborescence de répertoires — avant et après chaque appel d'outil, et diffe les instantanés en deltas create/update/delete par objet. Il ne demande jamais aux outils ce qui a changé : un effet est vu que la réponse le mentionne ou non.
- **Sonde** (`effects/probes.py`) : tente d'*utiliser* un objet créé comme credential contre la vraie règle d'autorisation du service. « Authority-bearing » est alors un résultat observé (l'objet a autorisé une action), pas une supposition tirée d'un nom de champ ; « encore effectif » signifie que la sonde réussit maintenant, pas que l'objet est encore listé.
- **Le lignage, en trois champs séparés** : `created_via` (quel appel a produit l'objet — observé), `authorized_by` (le grant sous lequel la session tournait — déclaré), et `depends_on` (ce que son efficacité continue exige réellement — établi en révoquant chaque candidat hors bande, en ré-exerçant, puis en restaurant). La distinction est le point : une clé d'API `authorized_by` un grant dont le `depends_on` n'inclut pas ce grant survit à sa révocation.
- **Banc d'essai** (`testbed/`) : un serveur MCP déterministe adossé à SQLite, avec des objets persistants ordinaires (notes) et des objets credentials (clés d'API, webhooks, liens de partage), un grant à un bit, des outils de cycle de vie, et des drapeaux de mutation qui plantent exactement un mensonge d'annotation chacun — calqués sur des motifs d'incidents documentés (un chemin de lecture qui frappe de l'autorité ; une révocation qui ne cascade pas). La vérité terrain est lue hors bande par `testbed/saas_oracle.py`, jamais via la surface MCP auditée.

Trois expériences tournent contre lui (`python experiments/run_all.py` — pipeline déterministe, que la CI rejoue en imposant des sorties identiques à l'octet). Chacune a un rôle distinct — E1 est l'expérience de détection, E2 une validation de construit (la distinction persistance/autorité est opérationnellement réelle), E3 une mesure de cycle de vie (existence ≠ efficacité courante). Les chiffres sont une performance de détection sur des incohérences plantées dans ce cadre contrôlé — **pas une prévalence en production** :

| Expérience | Sonde / observation d'effets | Baselines |
|---|---|---|
| **E1 · détection** — effet déclaré vs observé, serveur honnête + 6 variantes à mensonge unique ; oracle = le registre des mutations | precision / recall **1.000 / 1.000** | niveau réponse 1.000 / 0.333 · heuristique de nom 1.000 / 0.333 |
| **E2 · validation de construit** — authority-bearing vs simplement persistant, corpus de 8 objets dont une note-leurre nommée `api_key_backup` et un credential jamais persisté ; oracle = étiquettes d'autorité par construction | exactitude **1.000** sur le corpus construit pour séparer les signaux | mot-clé de nom 0.875 · persistance⇒autorité 0.625 |
| **E3 · mesure de cycle de vie** — existence vs efficacité courante sur 6 scénarios de cycle de vie (grant révoqué, clé révoquée, clé supprimée, TTL expiré, cascade) ; oracle = efficacité voulue par scénario | exactitude **1.000**, 0 faux-inefficace | existence 0.500 · statut du grant 0.333, 1 faux-inefficace |

Les deux résultats qui motivent le volet : dans E1, les trois mensonges dont les effets n'apparaissent jamais dans la réponse (`silent-keymint`, `shadow-webhook`, `phantom-write`) ne sont attrapés que par le diff d'état — un auditeur limité aux réponses leur est structurellement aveugle, d'où le recall de 0.333 des deux baselines. Dans le scénario `grant_revoked` d'E3, la clé créée sous le grant reste effective après la révocation du grant (la règle d'autorisation du banc d'essai consulte la ligne de la clé, pas le grant — la même forme que les incidents documentés de persistance d'applications OAuth) ; le proxy « statut du grant » la déclare neutralisée, et c'est l'unique faux-inefficace dangereux du tableau — `authorized_by` lu comme s'il s'agissait de `depends_on`.

**Et hors du banc d'essai** : trois études de cas pointent le même instrument vers des serveurs tiers publiés — le serveur memory officiel (store JSONL, entièrement annoté), le serveur filesystem officiel (répertoire cloisonné, observateur standard, entièrement annoté) et un serveur SQLite communautaire (aucune annotation). Chaque déclaration vérifiable a tenu ; là où rien n'était déclaré, les contrôles ont SKIPpé au lieu d'inventer un verdict ; et l'exécution filesystem a exposé un véritable angle mort de la première implémentation d'EFF-02 (un appel create+delete dont l'effet de tête cachait la suppression), désormais corrigé et épinglé par un test. Le versant sonde est resté honnêtement `unknown` de bout en bout — aucun de ces services ne frappe de credential exerçable — les résultats d'autorité par sonde restent donc validés sur banc d'essai. Preuves : [études de cas sur le site d'évaluation](https://yucpbit.github.io/mcp-proof/evaluation/#cases).

Méthodologie, conception de l'oracle, baselines, travaux connexes et limites : [docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) · résultats avec preuves brutes : [site d'évaluation](https://yucpbit.github.io/mcp-proof/evaluation/) · reproduction : [experiments/README.md](experiments/README.md).

## 🧭 Rapport à la suite de conformité officielle

Le projet MCP maintient [`modelcontextprotocol/conformance`](https://github.com/modelcontextprotocol/conformance) — des tests de scénarios qui vérifient le comportement protocolaire des serveurs et des clients, flux d'authentification compris. S'il vous faut une base de correction protocolaire, lancez-la ; le volet conformité de mcp-proof couvre un terrain qui la recoupe, depuis ses propres sondes au niveau du wire.

mcp-proof existe pour la moitié que la suite officielle ne fait pas : la **preuve de livraison**. Un rapport empreinté et vérifiable hors ligne que le client peut conserver ; la correspondance MSSS ; la régression comportementale dorée avec porte d'intégrité fail-closed ; l'instantané/diff contractuel comme porte de CI ; les artefacts SARIF/JUnit ; et le volet de recherche sur la conformité d'effets. Utilisez la suite officielle pour prouver le protocole ; utilisez mcp-proof pour prouver la livraison — les deux se composent, et la validation croisée avec la suite officielle est sur la feuille de route.

## 📡 Support protocolaire

| | |
|---|---|
| Transports | stdio ✅ · Streamable HTTP ✅ |
| Surfaces | tools ✅ · resources ✅ · prompts ✅ — sensibles aux capabilities dans les deux sens |
| Génération moderne `2026-07-28` (`server/discover`, `_meta` sans état) | ✅ volet conformité, auto-détectée — `--era auto\|modern\|legacy` |
| Génération legacy (handshake initialize, `2024-11-05` → `2025-11-25`) | ✅ tous les volets |
| Volet régression | ✅ les deux générations — session SDK (legacy) · session sonde (moderne) |

Fonctionne avec des serveurs écrits dans **n'importe quel langage** — mcp-proof parle au processus (ou à l'URL), pas à votre base de code.

## ⚙️ CI en une étape

```yaml
- uses: YuCPbit/mcp-proof@v0.8.1
  with:
    server-command: python my_server.py
    fixtures: fixtures/
```

Le job échoue tant que le serveur n'est pas ship-ready, et laisse `mcp-proof-report.html` / `.json` / `.junit.xml` / `.sarif` à téléverser. Vous préférez les commandes brutes ? `mcp-proof run … --junit r.xml --sarif r.sarif` plus `mcp-proof diff` constituent la même porte.

## 🏗️ Partir du gabarit propre à l'audit

Vous construisez un serveur plutôt que vous n'en auditez un ? [`templates/server-starter/`](templates/server-starter/) est un serveur fastmcp qui passe cet audit d'emblée — schémas d'entrée contraints, sémantique d'erreurs correcte, sortie structurée, chaque pratique annotée de l'identifiant du contrôle qu'elle satisfait. Copiez, implémentez vos outils, auditez, livrez avec le rapport.

## 🖥️ Plateformes

| | |
|---|---|
| macOS | ✅ développement et validation complète |
| Linux | ✅ exercé en CI |
| Windows | ✅ exercé en CI (`--pdf` nécessite Chrome/Chromium) |

## 🗺️ Feuille de route

| | |
|---|---|
| **Actuel — v0.8.1** | Durcissement recherche : trois études de cas tierces avec preuves committées (serveurs memory + filesystem officiels, serveur SQLite communautaire) ; contrôles d'effets alignés exactement sur les défauts d'annotation de la spec (l'absence d'un hint n'est jamais signalée) ; attribution des suppressions par cible (un appel create+delete ne peut pas cacher sa suppression) ; canal d'observation `--fs-root` ; reproduction des expériences identique à l'octet imposée par la CI |
| **v0.8.0** | Volet de recherche effect-aware : observation d'effets hors bande, classification d'autorité par sonde, mesure de l'autorité résiduelle (`mcp-proof effects`, [`experiments/`](experiments/), [docs](docs/effect-aware-conformance.md)) ; correction de la confiance aux annotations ; le [site d'évaluation](https://yucpbit.github.io/mcp-proof/evaluation/) |
| **v0.7.2** | Correctif de véracité : `verify` empreinte le document entier (schéma v3), le retrait du hash d'une fixture vaut falsification, baselines legacy fail-closed, taxonomie unique des codes de sortie |
| **Ensuite** | Approfondissement 2026-07-28 : allers-retours MRTR `input_required` · validation croisée avec la suite officielle en CI · un adaptateur de **sonde** pour fournisseur réel — exercer les credentials créés contre un fournisseur vivant ; le versant observation est déjà exercé sur des serveurs tiers |
| **Plus tard** | Lots de preuves signés (attestation) · volet sémantique opt-in (assertions notées par LLM) — en attente jusqu'à l'achèvement du cœur déterministe |

L'historique des versions vit dans [CHANGELOG.md](CHANGELOG.md).

## 🔍 Limites

mcp-proof prouve ce qui peut l'être de façon déterministe, et dit lequel est lequel :

- Les contrôles de sécurité couvrent la surface protocolaire et métadonnées observable. Les contrôles MSSS exigeant des preuves de déploiement, de source ou de processus sont toujours rapportés **manual review** — jamais supposés satisfaits.
- **Les flux d'autorisation sont hors périmètre** du rapport de livraison : les handshakes OAuth ne sont pas audités (la suite officielle couvre les scénarios d'auth). Le volet effets raisonne sur les *objets porteurs d'autorité* qu'un outil crée, sur un banc d'essai contrôlé avec observateur hors bande — il n'audite pas un déploiement OAuth de production.
- **Le volet effets est un instrument de mesure, pas un volet boîte noire.** Il lui faut un canal d'observation (`--sqlite`, `--fs-root`) ; les effets vers des systèmes qu'il ne peut observer sont rapportés `unknown`/SKIP, jamais supposés absents. Ses résultats quantitatifs sont une performance de détection sur banc synthétique — les études de cas montrent l'instrument fonctionnant sur des serveurs tiers, mais elles ne valident que le versant observation : l'autorité/efficacité par sonde reste validée sur banc d'essai. Voir [docs/effect-aware-conformance.md](docs/effect-aware-conformance.md) §8.
- L'auto-baseline classe les outils par une heuristique conservatrice de nom/description ; depuis la v0.8, un `readOnlyHint` non vérifié ne la contourne plus. Relisez la liste des sauts dans le manifeste des fixtures avant de faire confiance à une baseline enregistrée contre la production.
- La justesse sémantique (la réponse *veut-elle dire* la bonne chose ?) est, par conception, hors du cœur déterministe.

## 📄 Licence

MIT — la taxonomie de la section de conformité MSSS suit le [MCP Server Security Standard](https://mcp-security-standard.org) (CC BY-SA 4.0).
