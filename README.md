# TikTok Downloader

Petit outil **local** pour télécharger des vidéos TikTok **sans filigrane**, en **qualité maximale**, ou en **MP3**. Tout tourne sur ton PC : une interface web toute simple sur `http://127.0.0.1:5050`, rien n'est envoyé ailleurs.

## Fonctionnalités

- 🎬 **Qualité max sans filigrane** : la meilleure résolution dispo (souvent 1080p, H.265)
- 🎞️ **H.264 compatible partout** : Windows, iPhone, logiciels de montage…
- 🎵 **MP3 320 kbps** : le son extrait directement de la vidéo
- 🛠️ **Réparation auto des edits « patchés »** : les vidéos trafiquées pour « contourner la compression TikTok » (faux paquets, rotation cachée, en-têtes cassés) font souvent planter les lecteurs PC. L'outil les détecte et les réencode en H.264/AAC propre.
- 🧼 **Remux sans perte** des autres vidéos pour assainir le conteneur MP4 (durée « inconnue », etc.)
- 📋 Bouton **Coller** pour coller le lien en un clic

## Installation

### Prérequis

- [Python 3.10+](https://www.python.org/downloads/) (coche « Add Python to PATH » à l'installation)
- [FFmpeg](https://ffmpeg.org/download.html) dans le PATH (nécessaire pour le MP3 et la réparation des vidéos)
  ```powershell
  winget install Gyan.FFmpeg
  ```

### Lancement (Windows)

1. Télécharge la [dernière release](../../releases/latest) et dézippe-la
2. Double-clique sur **`lancer.bat`**

Le script installe/met à jour les dépendances (`flask`, `yt-dlp`), ouvre le navigateur et démarre le serveur.

### Lancement manuel

```bash
pip install -r requirements.txt
python app.py
```

Puis ouvre <http://127.0.0.1:5050>.

## Utilisation

1. Copie le lien d'une vidéo TikTok (`tiktok.com/...` ou `vm.tiktok.com/...`)
2. Colle-le dans le champ et clique sur **Analyser**
3. Choisis **Qualité max**, **H.264** ou **MP3**

## Astuce

TikTok change régulièrement son site. Si les téléchargements échouent, mets à jour `yt-dlp` :

```bash
python -m pip install -U yt-dlp
```

(`lancer.bat` le fait automatiquement à chaque démarrage.)

## Avertissement

Outil destiné à un usage personnel. Respecte les droits des créateurs et les conditions d'utilisation de TikTok : ne republie pas le contenu des autres sans leur accord.
