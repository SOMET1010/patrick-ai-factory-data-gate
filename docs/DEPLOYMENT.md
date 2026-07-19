# Déploiement sur le serveur

Objectif : mettre à jour la Data Gate sur le serveur **sans copier-coller**.
Trois options, du plus automatisé au plus simple. **Aucun secret ne doit jamais
apparaître dans le dépôt, dans une conversation, ou dans un log.**

---

## Option A — Déploiement automatique via GitHub Actions (recommandé)

À chaque merge sur `main`, GitHub se connecte en SSH au serveur et lance
[`scripts/deploy.sh`](../scripts/deploy.sh) (`git reset --hard origin/main` +
`pip install -e .` dans le venv). Zéro intervention ensuite.

### Réglage unique (à faire une seule fois)

1. **Générer une clé SSH dédiée au déploiement** (sur ta machine, *pas* sur le serveur) :
   ```bash
   ssh-keygen -t ed25519 -C "datagate-deploy" -f datagate_deploy -N ""
   ```
   Cela crée `datagate_deploy` (privée) et `datagate_deploy.pub` (publique).

2. **Autoriser la clé publique sur le serveur** (une ligne dans `authorized_keys`
   d'un utilisateur *non-root* dédié, ex. `deploy`) :
   ```bash
   ssh-copy-id -i datagate_deploy.pub deploy@<HOST>
   # ou : cat datagate_deploy.pub | ssh deploy@<HOST> 'cat >> ~/.ssh/authorized_keys'
   ```

3. **Cloner une fois le dépôt sur le serveur** à l'emplacement voulu :
   ```bash
   sudo mkdir -p /opt/patrick-ai-factory
   sudo chown deploy /opt/patrick-ai-factory
   git clone https://github.com/SOMET1010/patrick-ai-factory-data-gate \
     /opt/patrick-ai-factory/patrick-ai-factory-data-gate
   ```

4. **Ajouter les secrets et variables dans GitHub**
   (*Settings → Secrets and variables → Actions*) :

   | Type | Nom | Valeur |
   |---|---|---|
   | Secret | `DEPLOY_SSH_KEY` | le **contenu** du fichier privé `datagate_deploy` |
   | Secret | `DEPLOY_SSH_HOST` | l'IP ou le DNS du serveur |
   | Secret | `DEPLOY_SSH_USER` | l'utilisateur SSH (ex. `deploy`) |
   | Variable | `DATAGATE_HOME` | (optionnel) chemin d'install si différent du défaut |
   | Variable | `DEPLOY_ENABLED` | `true` pour activer le workflow |

   > La clé **privée** ne se colle **que** dans le champ secret GitHub — jamais
   > dans une conversation ni dans le code. GitHub la chiffre et la masque dans les logs.

5. C'est tout. Le prochain merge sur `main` déploie automatiquement. On peut aussi
   lancer à la demande via *Actions → Deploy → Run workflow*.

---

## Option B — Faire tourner un agent directement sur le serveur

Installer Claude Code sur le serveur donne à un agent un accès shell natif à
`/opt/patrick-ai-factory`. À faire sur le serveur :

```bash
# Node 18+ requis
npm install -g @anthropic-ai/claude-code
cd /opt/patrick-ai-factory/patrick-ai-factory-data-gate
claude   # première fois : authentification
```

L'agent peut alors déployer, lancer les vérifications et lire les logs sur place.

---

## Option C — Script manuel (une commande)

Sans automatisation, se connecter au serveur et lancer le script versionné :

```bash
ssh deploy@<HOST>
cd /opt/patrick-ai-factory/patrick-ai-factory-data-gate
git pull && ./scripts/deploy.sh
```

---

## Faire tourner la Data Gate périodiquement (optionnel)

Une fois installée, on peut planifier une vérification régulière du schéma via
`cron` (le DSN reste dans un fichier d'environnement protégé, jamais commité) :

```cron
# /etc/cron.d/datagate  — vérifie le schéma toutes les heures
0 * * * * deploy  cd /opt/patrick-ai-factory/patrick-ai-factory-data-gate \
  && . .venv/bin/activate \
  && set -a && . /etc/datagate.env && set +a \
  && datagate contracts/hermes-review.yaml -o artifacts/data-gate-result.json
```

`/etc/datagate.env` contient uniquement `DATAGATE_DSN=...` (rôle lecture seule),
avec des permissions restreintes (`chmod 600`).
