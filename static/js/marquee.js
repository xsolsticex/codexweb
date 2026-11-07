const garageStrip = document.querySelector('.garage-strip');
const garagePause = document.querySelector('.garage-pause');
garagePause.addEventListener('click', () => {
  const paused = garageStrip.classList.toggle('is-paused');
  garagePause.setAttribute('aria-pressed', String(paused));
  garagePause.setAttribute('aria-label', paused ? 'Reanudar letrero' : 'Pausar letrero');
  garagePause.textContent = paused ? '▶' : 'Ⅱ';
});
