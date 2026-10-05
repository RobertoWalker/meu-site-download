import os
import shutil
import tempfile
import threading
import time
import uuid
import zipfile

import yt_dlp
from flask import Flask, jsonify, request, send_file

app = Flask(__name__)

# Máximo de vídeos por playlist (pra não encher o disco sem querer).
# Se quiser mudar, é só trocar este número.
LIMITE_PLAYLIST = 50

# Guarda o andamento de cada download (o "painel de controle" do servidor)
JOBS = {}

PAGINA = """
<!DOCTYPE html>
<html lang="pt-br" data-tema="escuro" data-cor="roxo">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Baixar Vídeo</title>
  <script>
    // Aplica o tema salvo antes da página aparecer (evita piscar)
    try {
      const t = localStorage.getItem('tema');
      const c = localStorage.getItem('cor');
      if (t) document.documentElement.dataset.tema = t;
      if (c) document.documentElement.dataset.cor = c;
    } catch (e) {}
  </script>
  <style>
    /* ---------- Temas (claro/escuro) ---------- */
    :root {
      --fundo: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
      --texto: #f1f1f5;
      --texto-suave: #a9a9c4;
      --vidro: rgba(255, 255, 255, 0.06);
      --borda: rgba(255, 255, 255, 0.12);
      --campo: rgba(255, 255, 255, 0.1);
      --campo-fraco: rgba(255, 255, 255, 0.08);
      --sombra: 0 20px 60px rgba(0, 0, 0, 0.45);
      --opcao-fundo: #24243e;
      --erro-fundo: rgba(255, 90, 90, 0.15);
      --erro-texto: #ff9b9b;
    }
    [data-tema="claro"] {
      --fundo: linear-gradient(135deg, #eef1ff, #f7f0ff, #e9f4ff);
      --texto: #1d1d2e;
      --texto-suave: #5d5d78;
      --vidro: rgba(255, 255, 255, 0.75);
      --borda: rgba(0, 0, 0, 0.08);
      --campo: rgba(0, 0, 0, 0.06);
      --campo-fraco: rgba(0, 0, 0, 0.05);
      --sombra: 0 20px 60px rgba(60, 60, 120, 0.18);
      --opcao-fundo: #ffffff;
      --erro-fundo: rgba(220, 50, 50, 0.1);
      --erro-texto: #c62828;
    }

    /* ---------- Cores de destaque ---------- */
    :root, [data-cor="roxo"]    { --c1: #7c83ff; --c2: #b06cff; }
    [data-cor="azul"]           { --c1: #3b9eff; --c2: #5b7bff; }
    [data-cor="verde"]          { --c1: #20c997; --c2: #5fd35f; }
    [data-cor="vermelho"]       { --c1: #ff5d6c; --c2: #ff8a5c; }
    [data-cor="laranja"]        { --c1: #ff9f43; --c2: #ffc145; }

    * { box-sizing: border-box; }
    body {
      margin: 0; min-height: 100vh; display: flex; align-items: center;
      justify-content: center; font-family: 'Segoe UI', Arial, sans-serif;
      color: var(--texto); background: var(--fundo); background-attachment: fixed;
      padding: 30px 0; transition: background 0.3s, color 0.3s;
    }
    .cartao {
      position: relative; width: 92%; max-width: 520px; padding: 36px 30px;
      text-align: center; background: var(--vidro);
      border: 1px solid var(--borda); border-radius: 20px;
      backdrop-filter: blur(12px); box-shadow: var(--sombra);
    }
    .logo { font-size: 46px; margin-bottom: 4px; }
    h1 { margin: 0 0 6px; font-size: 28px; }
    .sub { margin: 0 0 22px; color: var(--texto-suave); font-size: 15px; }

    /* ---------- Barra de personalização ---------- */
    .topo {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 14px;
    }
    .cores { display: flex; gap: 8px; }
    .cor {
      width: 22px; height: 22px; border-radius: 50%; border: 2px solid transparent;
      cursor: pointer; padding: 0; margin: 0; box-shadow: none;
      transition: transform 0.15s;
    }
    .cor:hover { transform: scale(1.15); }
    .cor.ativa { border-color: var(--texto); }
    .cor[data-escolha="roxo"]     { background: linear-gradient(135deg, #7c83ff, #b06cff); }
    .cor[data-escolha="azul"]     { background: linear-gradient(135deg, #3b9eff, #5b7bff); }
    .cor[data-escolha="verde"]    { background: linear-gradient(135deg, #20c997, #5fd35f); }
    .cor[data-escolha="vermelho"] { background: linear-gradient(135deg, #ff5d6c, #ff8a5c); }
    .cor[data-escolha="laranja"]  { background: linear-gradient(135deg, #ff9f43, #ffc145); }
    #btnTema {
      width: 38px; height: 38px; margin: 0; padding: 0; font-size: 18px;
      border-radius: 50%; background: var(--campo); box-shadow: none;
      border: 1px solid var(--borda);
    }
    #btnTema:hover { transform: none; box-shadow: none; filter: brightness(1.15); }

    input[type=text] {
      width: 100%; padding: 15px 16px; border-radius: 12px; font-size: 16px;
      border: 2px solid transparent; background: var(--campo);
      color: var(--texto); outline: none; transition: border-color 0.2s;
    }
    input[type=text]::placeholder { color: var(--texto-suave); }
    input[type=text]:focus { border-color: var(--c1); }

    .opcao-playlist {
      display: flex; align-items: center; gap: 8px; margin-top: 12px;
      font-size: 14px; color: var(--texto-suave); cursor: pointer; text-align: left;
    }
    .opcao-playlist input {
      accent-color: var(--c1); width: 16px; height: 16px;
      cursor: pointer; flex-shrink: 0;
    }

    .previa {
      display: none; margin-top: 16px; border-radius: 14px; overflow: hidden;
      background: var(--campo-fraco); text-align: left;
    }
    .previa img { width: 100%; display: block; aspect-ratio: 16 / 9; object-fit: cover; background: #1b1b2f; }
    .previa .info { padding: 12px 14px; }
    .previa .titulo { font-weight: 600; font-size: 15px; line-height: 1.35; }
    .previa .detalhes { margin-top: 4px; color: var(--texto-suave); font-size: 13px; }
    .status { margin-top: 14px; font-size: 14px; color: var(--texto-suave); display: none; }
    .status.erro-link { color: var(--erro-texto); }

    .formatos { display: flex; gap: 10px; margin-top: 16px; }
    .formatos label { flex: 1; cursor: pointer; }
    .formatos input { display: none; }
    .formatos span {
      display: block; padding: 12px; border-radius: 12px; font-size: 15px;
      background: var(--campo-fraco); transition: all 0.2s;
    }
    .formatos input:checked + span {
      color: #fff; background: linear-gradient(135deg, var(--c1), var(--c2));
      box-shadow: 0 6px 18px rgba(0, 0, 0, 0.25);
    }

    select {
      width: 100%; margin-top: 12px; padding: 13px 14px; border-radius: 12px;
      border: none; font-size: 15px; background: var(--campo);
      color: var(--texto); outline: none; cursor: pointer;
    }
    select option { background: var(--opcao-fundo); color: var(--texto); }
    .dica-audio {
      display: none; margin-top: 8px; font-size: 12px;
      color: var(--texto-suave); text-align: left;
    }

    #btn {
      width: 100%; margin-top: 20px; padding: 16px; border: none;
      border-radius: 12px; font-size: 17px; font-weight: 600; color: #fff;
      cursor: pointer; background: linear-gradient(135deg, var(--c1), var(--c2));
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
      transition: transform 0.15s, box-shadow 0.15s;
      display: flex; align-items: center; justify-content: center; gap: 10px;
    }
    #btn:hover { transform: translateY(-2px); box-shadow: 0 12px 30px rgba(0, 0, 0, 0.35); }
    #btn:active { transform: translateY(0); }
    #btn:disabled { opacity: 0.8; cursor: wait; transform: none; }

    .spinner {
      display: none; width: 18px; height: 18px; border-radius: 50%;
      border: 3px solid rgba(255, 255, 255, 0.35); border-top-color: #fff;
      animation: girar 0.8s linear infinite;
    }
    #btn.carregando .spinner { display: block; }
    @keyframes girar { to { transform: rotate(360deg); } }

    .progresso { display: none; margin-top: 18px; }
    .barra { height: 12px; border-radius: 999px; overflow: hidden; background: var(--campo); }
    .preenchido {
      height: 100%; width: 0%; border-radius: 999px;
      background: linear-gradient(90deg, var(--c1), var(--c2));
      transition: width 0.4s ease;
    }
    .progresso-texto { margin-top: 8px; font-size: 14px; color: var(--texto-suave); }

    .erro {
      display: none; margin-top: 18px; padding: 12px; border-radius: 10px;
      font-size: 14px; background: var(--erro-fundo); color: var(--erro-texto);
    }

    /* ---------- Histórico ---------- */
    .historico { display: none; margin-top: 28px; text-align: left; }
    .historico-topo {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 10px;
    }
    .historico-topo h2 { margin: 0; font-size: 16px; }
    #btnLimpar {
      width: auto; margin: 0; padding: 6px 12px; font-size: 13px; font-weight: 500;
      border-radius: 8px; background: var(--campo); color: var(--texto-suave);
      box-shadow: none; border: none; cursor: pointer;
    }
    #btnLimpar:hover { color: var(--erro-texto); }
    .item {
      display: flex; align-items: center; gap: 10px; padding: 10px 12px;
      margin-bottom: 8px; border-radius: 12px; background: var(--campo-fraco);
      cursor: pointer; transition: background 0.15s;
    }
    .item:hover { background: var(--campo); }
    .item .icone { font-size: 20px; }
    .item .dados { flex: 1; min-width: 0; }
    .item .nome {
      font-size: 14px; font-weight: 600;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .item .meta { font-size: 12px; color: var(--texto-suave); margin-top: 2px; }
  </style>
</head>
<body>
  <div class="cartao">
    <div class="topo">
      <div class="cores" id="cores">
        <button type="button" class="cor" data-escolha="roxo" title="Roxo"></button>
        <button type="button" class="cor" data-escolha="azul" title="Azul"></button>
        <button type="button" class="cor" data-escolha="verde" title="Verde"></button>
        <button type="button" class="cor" data-escolha="vermelho" title="Vermelho"></button>
        <button type="button" class="cor" data-escolha="laranja" title="Laranja"></button>
      </div>
      <button type="button" id="btnTema" title="Alternar tema claro/escuro">🌙</button>
    </div>

    <div class="logo">⬇️</div>
    <h1>Baixar Vídeo</h1>
    <p class="sub">Cole o link, confira a prévia e baixe.</p>

    <form id="form">
      <input type="text" id="link" placeholder="Cole o link do vídeo aqui" required autocomplete="off">

      <label class="opcao-playlist">
        <input type="checkbox" id="chkPlaylist">
        <span>📚 É uma playlist: baixar todos os vídeos (vira um ZIP)</span>
      </label>

      <div class="status" id="status"></div>

      <div class="previa" id="previa">
        <img id="miniatura" alt="Miniatura do vídeo" referrerpolicy="no-referrer">
        <div class="info">
          <div class="titulo" id="titulo"></div>
          <div class="detalhes" id="detalhes"></div>
        </div>
      </div>

      <div class="formatos">
        <label><input type="radio" name="formato" value="video" checked><span>🎬 Vídeo (MP4)</span></label>
        <label><input type="radio" name="formato" value="mp3"><span>🎵 Só áudio (MP3)</span></label>
      </div>

      <select id="qualidade">
        <option value="melhor">Qualidade do vídeo: melhor disponível</option>
        <option value="1080">Qualidade do vídeo: 1080p</option>
        <option value="720">Qualidade do vídeo: 720p</option>
        <option value="480">Qualidade do vídeo: 480p</option>
        <option value="360">Qualidade do vídeo: 360p</option>
      </select>

      <select id="qualidadeAudio" style="display: none;">
        <option value="128">Qualidade do áudio: 128 kbps (menor arquivo)</option>
        <option value="192" selected>Qualidade do áudio: 192 kbps (equilibrado)</option>
        <option value="256">Qualidade do áudio: 256 kbps (alta)</option>
        <option value="320">Qualidade do áudio: 320 kbps (máxima)</option>
      </select>
      <div class="dica-audio" id="dicaAudio">
        Quanto maior o número, maior o arquivo. Se o áudio original do vídeo já for de qualidade menor, subir demais não melhora o som.
      </div>

      <button id="btn" type="submit">
        <div class="spinner"></div>
        <span id="texto">Baixar</span>
      </button>
    </form>

    <div class="progresso" id="progresso">
      <div class="barra"><div class="preenchido" id="preenchido"></div></div>
      <div class="progresso-texto" id="progressoTexto"></div>
    </div>

    <div class="erro" id="erro"></div>

    <div class="historico" id="historico">
      <div class="historico-topo">
        <h2>🕘 Histórico</h2>
        <button type="button" id="btnLimpar">Limpar</button>
      </div>
      <div id="listaHistorico"></div>
    </div>
  </div>

  <script>
    const raiz = document.documentElement;
    const form = document.getElementById('form');
    const btn = document.getElementById('btn');
    const texto = document.getElementById('texto');
    const campoLink = document.getElementById('link');
    const chkPlaylist = document.getElementById('chkPlaylist');
    const previa = document.getElementById('previa');
    const status = document.getElementById('status');
    const erroBox = document.getElementById('erro');
    const progresso = document.getElementById('progresso');
    const preenchido = document.getElementById('preenchido');
    const progressoTexto = document.getElementById('progressoTexto');
    const selVideo = document.getElementById('qualidade');
    const selAudio = document.getElementById('qualidadeAudio');
    const dicaAudio = document.getElementById('dicaAudio');
    let espera = null;
    let numeroBusca = 0;
    let tituloAtual = '';
    let quantidadeAtual = 0;

    // ---------- Armazenamento seguro (não quebra se o navegador bloquear) ----------
    function guardar(chave, valor) {
      try { localStorage.setItem(chave, valor); } catch (e) {}
    }
    function ler(chave) {
      try { return localStorage.getItem(chave); } catch (e) { return null; }
    }

    // ---------- Tema e cores ----------
    const btnTema = document.getElementById('btnTema');

    function marcarCorAtiva() {
      document.querySelectorAll('.cor').forEach(function (b) {
        b.classList.toggle('ativa', b.dataset.escolha === raiz.dataset.cor);
      });
    }

    function atualizarIconeTema() {
      btnTema.textContent = raiz.dataset.tema === 'claro' ? '☀️' : '🌙';
    }

    btnTema.addEventListener('click', function () {
      raiz.dataset.tema = raiz.dataset.tema === 'claro' ? 'escuro' : 'claro';
      guardar('tema', raiz.dataset.tema);
      atualizarIconeTema();
    });

    document.getElementById('cores').addEventListener('click', function (e) {
      const alvo = e.target.closest('.cor');
      if (!alvo) return;
      raiz.dataset.cor = alvo.dataset.escolha;
      guardar('cor', alvo.dataset.escolha);
      marcarCorAtiva();
    });

    marcarCorAtiva();
    atualizarIconeTema();

    // ---------- Mostra a qualidade certa (vídeo ou áudio) ----------
    function formatoEscolhido() {
      return document.querySelector('input[name=formato]:checked').value;
    }

    function atualizarOpcoes() {
      const ehMp3 = formatoEscolhido() === 'mp3';
      selVideo.style.display = ehMp3 ? 'none' : 'block';
      selAudio.style.display = ehMp3 ? 'block' : 'none';
      dicaAudio.style.display = ehMp3 ? 'block' : 'none';
    }

    document.querySelectorAll('input[name=formato]').forEach(function (radio) {
      radio.addEventListener('change', atualizarOpcoes);
    });
    atualizarOpcoes();

    // ---------- Histórico ----------
    const boxHistorico = document.getElementById('historico');
    const listaHistorico = document.getElementById('listaHistorico');

    function lerHistorico() {
      try {
        const lista = JSON.parse(ler('historico') || '[]');
        return Array.isArray(lista) ? lista : [];
      } catch (e) {
        return [];
      }
    }

    function formatarData(ms) {
      const d = new Date(ms);
      const dia = String(d.getDate()).padStart(2, '0');
      const mes = String(d.getMonth() + 1).padStart(2, '0');
      const hora = String(d.getHours()).padStart(2, '0');
      const min = String(d.getMinutes()).padStart(2, '0');
      return dia + '/' + mes + ' às ' + hora + ':' + min;
    }

    function descreverItem(item) {
      let base;
      if (item.formato === 'mp3') {
        base = item.audio ? 'MP3 • ' + item.audio + ' kbps' : 'MP3';
      } else {
        base = 'MP4 • ' + item.qualidade;
      }
      if (item.playlist) {
        base = 'Playlist' + (item.itens ? ' (' + item.itens + ' vídeos)' : '') + ' • ' + base;
      }
      return base;
    }

    function iconeItem(item) {
      if (item.playlist) return '📚';
      return item.formato === 'mp3' ? '🎵' : '🎬';
    }

    function desenharHistorico() {
      const lista = lerHistorico();
      listaHistorico.innerHTML = '';
      boxHistorico.style.display = lista.length ? 'block' : 'none';

      lista.forEach(function (item) {
        const linha = document.createElement('div');
        linha.className = 'item';
        linha.title = 'Clique para colar o link de novo';

        const icone = document.createElement('div');
        icone.className = 'icone';
        icone.textContent = iconeItem(item);

        const dados = document.createElement('div');
        dados.className = 'dados';

        const nome = document.createElement('div');
        nome.className = 'nome';
        nome.textContent = item.titulo;

        const meta = document.createElement('div');
        meta.className = 'meta';
        meta.textContent = descreverItem(item) + ' • ' + formatarData(item.quando);

        dados.appendChild(nome);
        dados.appendChild(meta);
        linha.appendChild(icone);
        linha.appendChild(dados);

        linha.addEventListener('click', function () {
          campoLink.value = item.link;
          chkPlaylist.checked = !!item.playlist;
          buscarPrevia();
          window.scrollTo({ top: 0, behavior: 'smooth' });
        });

        listaHistorico.appendChild(linha);
      });
    }

    function salvarNoHistorico(link, formato, qualidade, audio, playlist, itens) {
      let lista = lerHistorico();
      lista = lista.filter(function (i) {
        return !(i.link === link && i.formato === formato && !!i.playlist === playlist);
      });
      lista.unshift({
        link: link,
        titulo: tituloAtual || link,
        formato: formato,
        qualidade: qualidade === 'melhor' ? 'melhor qualidade' : qualidade + 'p',
        audio: audio,
        playlist: playlist,
        itens: itens,
        quando: Date.now()
      });
      guardar('historico', JSON.stringify(lista.slice(0, 15)));
      desenharHistorico();
    }

    document.getElementById('btnLimpar').addEventListener('click', function () {
      guardar('historico', '[]');
      desenharHistorico();
    });

    desenharHistorico();

    // ---------- Funções gerais ----------
    function linkValido(link) {
      const minusculo = link.toLowerCase();
      return minusculo.startsWith('http://') || minusculo.startsWith('https://');
    }

    function mostrarStatus(mensagem, ehErro) {
      status.style.display = mensagem ? 'block' : 'none';
      status.textContent = mensagem;
      status.className = ehErro ? 'status erro-link' : 'status';
    }

    function mostrarErro(mensagem) {
      erroBox.textContent = mensagem;
      erroBox.style.display = mensagem ? 'block' : 'none';
    }

    function resetarBotao() {
      btn.disabled = false;
      btn.classList.remove('carregando');
      texto.textContent = 'Baixar';
    }

    function atualizarBarra(porcentagem, mensagem) {
      preenchido.style.width = porcentagem + '%';
      progressoTexto.textContent = mensagem;
    }

    function formatarEta(segundos) {
      if (segundos === null || segundos === undefined) return '';
      if (segundos < 60) return segundos + 's';
      return Math.floor(segundos / 60) + 'min ' + (segundos % 60) + 's';
    }

    // ---------- Prévia do vídeo / playlist ----------
    async function buscarPrevia() {
      const link = campoLink.value.trim();
      const minhaBusca = ++numeroBusca;
      previa.style.display = 'none';
      tituloAtual = '';
      quantidadeAtual = 0;

      if (!link) { mostrarStatus('', false); return; }
      if (!linkValido(link)) {
        mostrarStatus('O link precisa começar com http:// ou https://', true);
        return;
      }

      mostrarStatus(
        chkPlaylist.checked ? 'Lendo a playlist...' : 'Buscando informações do vídeo...',
        false
      );
      try {
        const resp = await fetch('/info', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ link: link, playlist: chkPlaylist.checked })
        });
        const dados = await resp.json();
        if (minhaBusca !== numeroBusca) return;

        if (!resp.ok) {
          mostrarStatus(dados.erro || 'Não consegui ler esse link.', true);
          return;
        }

        tituloAtual = dados.titulo;
        quantidadeAtual = dados.playlist ? dados.quantidade : 0;

        document.getElementById('titulo').textContent =
          (dados.playlist ? '📚 ' : '') + dados.titulo;

        const partes = [dados.canal];
        if (dados.playlist) {
          let qtd = dados.quantidade + (dados.quantidade === 1 ? ' vídeo' : ' vídeos');
          if (dados.total > dados.quantidade) {
            qtd += ' (a playlist tem ' + dados.total + '; baixa só os primeiros ' + dados.quantidade + ')';
          }
          partes.push(qtd);
        } else {
          partes.push(dados.duracao);
        }
        document.getElementById('detalhes').textContent = partes.filter(Boolean).join(' • ');

        const img = document.getElementById('miniatura');
        if (dados.miniatura && dados.miniatura.startsWith('http')) {
          img.src = dados.miniatura;
          img.style.display = 'block';
        } else {
          img.style.display = 'none';
        }

        mostrarStatus('', false);
        previa.style.display = 'block';
      } catch (e) {
        if (minhaBusca !== numeroBusca) return;
        mostrarStatus('Erro ao buscar as informações. Tente de novo.', true);
      }
    }

    campoLink.addEventListener('input', function () {
      clearTimeout(espera);
      espera = setTimeout(buscarPrevia, 700);
    });

    chkPlaylist.addEventListener('change', buscarPrevia);

    // ---------- Download com barra de progresso ----------
    function acompanhar(id, link, formato, qualidade, audio, playlist, itens) {
      const timer = setInterval(async function () {
        try {
          const resp = await fetch('/progresso/' + id);
          const d = await resp.json();
          if (!resp.ok) throw new Error(d.erro || 'O download foi perdido.');

          if (d.estado === 'erro') {
            clearInterval(timer);
            mostrarErro(d.erro);
            progresso.style.display = 'none';
            resetarBotao();
            return;
          }

          if (d.estado === 'pronto') {
            clearInterval(timer);
            atualizarBarra(100, 'Pronto! Enviando o arquivo pro navegador...');
            salvarNoHistorico(link, formato, qualidade, audio, playlist, itens);
            window.location.href = '/arquivo/' + id;
            setTimeout(function () {
              progresso.style.display = 'none';
              resetarBotao();
            }, 2500);
            return;
          }

          if (d.estado === 'processando') {
            atualizarBarra(
              d.percentual,
              d.total_videos > 1 ? 'Compactando tudo num ZIP...' : 'Finalizando o arquivo...'
            );
            return;
          }

          let msg = '';
          if (d.total_videos > 1) {
            msg += 'Vídeo ' + d.video_atual + ' de ' + d.total_videos + ' • ';
          }
          msg += Math.floor(d.percentual) + '%';
          if (d.velocidade) msg += ' • ' + d.velocidade;
          const eta = formatarEta(d.eta);
          if (eta) msg += ' • faltam ' + eta;
          atualizarBarra(d.percentual, msg);
        } catch (err) {
          clearInterval(timer);
          mostrarErro(err.message);
          progresso.style.display = 'none';
          resetarBotao();
        }
      }, 1000);
    }

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      mostrarErro('');

      const link = campoLink.value.trim();
      if (!linkValido(link)) {
        mostrarErro('Cole um link válido, começando com http:// ou https://');
        return;
      }

      const formato = formatoEscolhido();
      const qualidade = selVideo.value;
      const audio = selAudio.value;
      const playlist = chkPlaylist.checked;
      const itens = quantidadeAtual;

      btn.disabled = true;
      btn.classList.add('carregando');
      texto.textContent = 'Baixando... aguarde';
      progresso.style.display = 'block';
      atualizarBarra(0, 'Iniciando...');

      try {
        const resp = await fetch('/iniciar', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            link: link,
            formato: formato,
            qualidade: qualidade,
            audio: audio,
            playlist: playlist
          })
        });
        const dados = await resp.json();
        if (!resp.ok) throw new Error(dados.erro || 'Não foi possível iniciar o download.');
        acompanhar(dados.id, link, formato, qualidade, audio, playlist, itens);
      } catch (err) {
        mostrarErro(err.message);
        progresso.style.display = 'none';
        resetarBotao();
      }
    });
  </script>
</body>
</html>
"""


def formatar_duracao(segundos):
    if not segundos:
        return ""
    segundos = int(segundos)
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    if horas:
        return f"{horas}:{minutos:02d}:{seg:02d}"
    return f"{minutos}:{seg:02d}"


def formatar_velocidade(bytes_por_segundo):
    if not bytes_por_segundo:
        return ""
    return f"{bytes_por_segundo / 1024 / 1024:.1f} MB/s"


def nome_seguro(texto):
    """Deixa só letras, números, espaço, - e _ (nome de arquivo seguro no Windows)."""
    limpo = "".join(c for c in texto if c.isalnum() or c in " -_").strip()
    return limpo[:80] or "playlist"


def remover_job(job_id):
    job = JOBS.pop(job_id, None)
    if job:
        shutil.rmtree(job["pasta"], ignore_errors=True)


def limpar_antigos():
    """Apaga downloads abandonados (mais de 1 hora) pra não encher o PC."""
    agora = time.time()
    for job_id, job in list(JOBS.items()):
        if agora - job["criado"] > 3600:
            remover_job(job_id)


def opcoes_de_lista():
    """Opções pra só LER a playlist (sem baixar nada)."""
    return {
        "quiet": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "noplaylist": False,
        "playlistend": LIMITE_PLAYLIST,
    }


def executar_download(job_id, link, formato, qualidade, audio, playlist):
    """Roda em segundo plano: baixa o vídeo (ou a playlist) e vai atualizando o andamento."""
    job = JOBS[job_id]

    def acompanhar_progresso(d):
        info = d.get("info_dict") or {}
        indice = info.get("playlist_index") or 1

        # Começou um vídeo novo da playlist: zera a contagem de arquivos dele
        if indice != job["video_atual"]:
            job["video_atual"] = indice
            job["concluidos_video"] = 0

        if d["status"] == "downloading":
            # Cada vídeo pode ser 1 arquivo (já com som) ou 2 (vídeo + áudio separados)
            if formato == "mp3":
                job["arquivos_video"] = 1
            else:
                combinado = (
                    info.get("vcodec") not in (None, "none")
                    and info.get("acodec") not in (None, "none")
                )
                job["arquivos_video"] = 1 if combinado else 2

            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            feito = d.get("downloaded_bytes") or 0
            fracao = min(feito / total, 1) if total else 0
            parte = min((job["concluidos_video"] + fracao) / job["arquivos_video"], 1)
            geral = ((job["video_atual"] - 1) + parte) / job["total_videos"] * 100

            # Nunca deixa a barra andar pra trás
            job["percentual"] = max(job["percentual"], min(round(geral, 1), 99))
            job["velocidade"] = formatar_velocidade(d.get("speed"))
            job["eta"] = d.get("eta")

        elif d["status"] == "finished":
            job["concluidos_video"] += 1
            if (
                job["video_atual"] >= job["total_videos"]
                and job["concluidos_video"] >= job["arquivos_video"]
            ):
                job["estado"] = "processando"
                job["percentual"] = 99

    try:
        titulo_playlist = ""

        if playlist:
            # Primeiro descobre quantos vídeos a playlist tem
            with yt_dlp.YoutubeDL(opcoes_de_lista()) as ydl:
                lista = ydl.extract_info(link, download=False)
            entradas = [e for e in (lista.get("entries") or []) if e]
            if not entradas:
                raise ValueError(
                    "Esse link não parece ser uma playlist. "
                    "Desmarque a opção se for um vídeo só."
                )
            job["total_videos"] = len(entradas)
            titulo_playlist = lista.get("title") or "playlist"

        modelo = (
            "%(playlist_index)03d - %(title).70s.%(ext)s"
            if playlist
            else "%(title).80s.%(ext)s"
        )

        opcoes = {
            "outtmpl": os.path.join(job["pasta"], modelo),
            "noplaylist": not playlist,
            "ignoreerrors": playlist,  # na playlist, pula vídeos indisponíveis
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [acompanhar_progresso],
        }
        if playlist:
            opcoes["playlistend"] = LIMITE_PLAYLIST

        if formato == "mp3":
            opcoes["format"] = "bestaudio/best"
            opcoes["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": audio,
            }]
        else:
            if qualidade in ("1080", "720", "480", "360"):
                opcoes["format"] = (
                    f"bestvideo[height<={qualidade}]+bestaudio/"
                    f"best[height<={qualidade}]"
                )
            else:
                opcoes["format"] = "bestvideo+bestaudio/best"
            opcoes["merge_output_format"] = "mp4"

        with yt_dlp.YoutubeDL(opcoes) as ydl:
            ydl.download([link])

        arquivos = [
            a for a in sorted(os.listdir(job["pasta"]))
            if not a.endswith((".part", ".ytdl"))
        ]
        if not arquivos:
            raise ValueError("Não consegui baixar nada desse link.")

        if playlist:
            # Junta tudo num ZIP (sem comprimir, porque vídeo já é comprimido)
            job["estado"] = "processando"
            job["percentual"] = 99
            nome_zip = nome_seguro(titulo_playlist) + ".zip"
            caminho_zip = os.path.join(job["pasta"], nome_zip)
            with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_STORED) as z:
                for nome in arquivos:
                    z.write(os.path.join(job["pasta"], nome), arcname=nome)
            for nome in arquivos:
                os.remove(os.path.join(job["pasta"], nome))
            job["arquivo"] = nome_zip
        else:
            job["arquivo"] = arquivos[0]

        job["percentual"] = 100
        job["estado"] = "pronto"
    except Exception as e:
        job["estado"] = "erro"
        if isinstance(e, ValueError):
            job["erro"] = str(e)
        else:
            job["erro"] = "Não consegui baixar esse vídeo. Confira o link e tente de novo."
        shutil.rmtree(job["pasta"], ignore_errors=True)


@app.route("/")
def home():
    return PAGINA


@app.route("/info", methods=["POST"])
def info():
    dados = request.get_json(silent=True) or {}
    link = str(dados.get("link", "")).strip()
    playlist = bool(dados.get("playlist", False))

    if not link.lower().startswith(("http://", "https://")):
        return jsonify(erro="Cole um link válido."), 400

    try:
        if playlist:
            with yt_dlp.YoutubeDL(opcoes_de_lista()) as ydl:
                d = ydl.extract_info(link, download=False)

            entradas = [e for e in (d.get("entries") or []) if e]
            if not entradas:
                return jsonify(
                    erro="Esse link não parece ser uma playlist. "
                         "Desmarque a opção se for um vídeo só."
                ), 400

            total = d.get("playlist_count") or len(entradas)
            miniatura = d.get("thumbnail") or (d.get("thumbnails") or [{}])[-1].get("url", "")
            return jsonify(
                playlist=True,
                titulo=d.get("title") or "Playlist",
                canal=d.get("uploader") or d.get("channel") or "",
                miniatura=miniatura or "",
                quantidade=min(total, LIMITE_PLAYLIST),
                total=total,
            )

        opcoes = {"quiet": True, "noplaylist": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            d = ydl.extract_info(link, download=False)

        return jsonify(
            playlist=False,
            titulo=d.get("title") or "Sem título",
            canal=d.get("uploader") or "",
            duracao=formatar_duracao(d.get("duration")),
            miniatura=d.get("thumbnail") or "",
        )
    except Exception:
        return jsonify(erro="Não consegui ler esse link. Confira e tente de novo."), 400


@app.route("/iniciar", methods=["POST"])
def iniciar():
    dados = request.get_json(silent=True) or {}
    link = str(dados.get("link", "")).strip()
    formato = dados.get("formato", "video")
    qualidade = dados.get("qualidade", "melhor")
    audio = str(dados.get("audio", "192"))
    playlist = bool(dados.get("playlist", False))

    if not link.lower().startswith(("http://", "https://")):
        return jsonify(erro="Cole um link válido, começando com http:// ou https://"), 400
    if formato not in ("video", "mp3"):
        formato = "video"
    if audio not in ("128", "192", "256", "320"):
        audio = "192"

    limpar_antigos()

    job_id = uuid.uuid4().hex
    JOBS[job_id] = {
        "estado": "baixando",
        "percentual": 0,
        "velocidade": "",
        "eta": None,
        "erro": "",
        "arquivo": "",
        "pasta": tempfile.mkdtemp(),
        "criado": time.time(),
        "total_videos": 1,
        "video_atual": 1,
        "arquivos_video": 1,
        "concluidos_video": 0,
    }

    thread = threading.Thread(
        target=executar_download,
        args=(job_id, link, formato, qualidade, audio, playlist),
        daemon=True,
    )
    thread.start()

    return jsonify(id=job_id)


@app.route("/progresso/<job_id>")
def progresso(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify(erro="Download não encontrado."), 404

    return jsonify(
        estado=job["estado"],
        percentual=job["percentual"],
        velocidade=job["velocidade"],
        eta=job["eta"],
        erro=job["erro"],
        video_atual=job["video_atual"],
        total_videos=job["total_videos"],
    )


@app.route("/arquivo/<job_id>")
def arquivo(job_id):
    job = JOBS.get(job_id)
    if not job or job["estado"] != "pronto":
        return jsonify(erro="Arquivo não disponível."), 404

    caminho = os.path.join(job["pasta"], job["arquivo"])
    resposta = send_file(caminho, as_attachment=True, download_name=job["arquivo"])

    # Apaga a pasta temporária 5 minutos depois (tempo de sobra pro navegador pegar o arquivo)
    apagador = threading.Timer(300, remover_job, args=(job_id,))
    apagador.daemon = True
    apagador.start()

    return resposta


if __name__ == "__main__":
    app.run(debug=True)