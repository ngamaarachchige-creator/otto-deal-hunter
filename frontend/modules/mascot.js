// Lanka Car Hunter · Interactive AI Scout Mascot (Bloub-style organic agent)

export class ScoutMascot {
  constructor(containerId = 'mascotContainer') {
    this.container = document.getElementById(containerId);
    if (!this.container) return;

    this.state = 'idle'; // idle, searching, excited, inspecting
    this.targetX = 0;
    this.targetY = 0;
    this.currX = 0;
    this.currY = 0;
    this.blinkProgress = 0;
    this.isBlinking = false;
    this.breathTime = 0;

    this.initCanvas();
    this.bindEvents();
    this.startLoop();
  }

  initCanvas() {
    this.container.innerHTML = '';
    this.canvas = document.createElement('canvas');
    this.canvas.width = 120;
    this.canvas.height = 120;
    this.canvas.style.width = '52px';
    this.canvas.style.height = '52px';
    this.canvas.style.cursor = 'pointer';
    this.canvas.title = 'Click me to say hi!';
    this.ctx = this.canvas.getContext('2d');
    this.container.appendChild(this.canvas);
  }

  bindEvents() {
    window.addEventListener('mousemove', (e) => {
      if (!this.canvas) return;
      const rect = this.canvas.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      const dx = e.clientX - cx;
      const dy = e.clientY - cy;
      const dist = Math.hypot(dx, dy);
      const maxDist = 7;
      const factor = Math.min(1, dist / 400);

      this.targetX = (dx / (dist || 1)) * maxDist * factor;
      this.targetY = (dy / (dist || 1)) * maxDist * factor;
    });

    if (this.canvas) {
      this.canvas.addEventListener('click', () => {
        this.triggerState('excited', 3000);
      });
    }

    setInterval(() => {
      if (Math.random() > 0.3 && !this.isBlinking) {
        this.blink();
      }
    }, 3500);
  }

  blink() {
    this.isBlinking = true;
    let progress = 0;
    const step = () => {
      progress += 0.2;
      if (progress <= 1) {
        this.blinkProgress = Math.sin(progress * Math.PI);
        requestAnimationFrame(step);
      } else {
        this.blinkProgress = 0;
        this.isBlinking = false;
      }
    };
    step();
  }

  triggerState(stateName, duration = 3000) {
    this.state = stateName;
    if (this.resetTimer) clearTimeout(this.resetTimer);
    this.resetTimer = setTimeout(() => {
      this.state = 'idle';
    }, duration);
  }

  startLoop() {
    const render = () => {
      this.update();
      this.draw();
      requestAnimationFrame(render);
    };
    requestAnimationFrame(render);
  }

  update() {
    this.breathTime += 0.04;
    this.currX += (this.targetX - this.currX) * 0.14;
    this.currY += (this.targetY - this.currY) * 0.14;
  }

  draw() {
    if (!this.ctx) return;
    const ctx = this.ctx;
    ctx.clearRect(0, 0, 120, 120);

    const cx = 60;
    const cy = 60;
    
    // Breathing squash & stretch
    const breathScaleY = 1 + Math.sin(this.breathTime) * 0.035;
    const breathScaleX = 1 - Math.sin(this.breathTime) * 0.025;

    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(breathScaleX, breathScaleY);

    // Mascot Body (Bloub deep ink #0f172a / #17203a)
    ctx.beginPath();
    ctx.fillStyle = '#0f172a';
    ctx.shadowColor = 'rgba(15, 23, 42, 0.18)';
    ctx.shadowBlur = 10;
    ctx.shadowOffsetY = 4;

    const r = 44;
    ctx.arc(0, 0, r, 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowColor = 'transparent';

    // Highlight rim
    ctx.beginPath();
    ctx.arc(0, -2, r - 2, Math.PI * 0.85, Math.PI * 2.15);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.14)';
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Eyes
    const eyeSpacing = 16;
    const eyeY = -4 + this.currY;
    const eyeXOffset = this.currX;

    const drawEye = (x) => {
      ctx.save();
      ctx.translate(x + eyeXOffset, eyeY);

      if (this.state === 'excited') {
        // Happy arch eyes (^ ^)
        ctx.beginPath();
        ctx.arc(0, 2, 7, Math.PI * 1.15, Math.PI * 1.85);
        ctx.strokeStyle = '#ffffff';
        ctx.lineWidth = 3.5;
        ctx.lineCap = 'round';
        ctx.stroke();
      } else if (this.state === 'searching') {
        // Scanning radar glow eye
        ctx.beginPath();
        const eyeHeight = Math.max(1, 8 * (1 - this.blinkProgress));
        ctx.ellipse(0, 0, 7.5, eyeHeight, 0, 0, Math.PI * 2);
        ctx.fillStyle = '#38bdf8';
        ctx.fill();
        ctx.beginPath();
        ctx.arc(0, 0, 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.fill();
      } else {
        // Normal wide curious eye
        const eyeHeight = Math.max(1, 8.5 * (1 - this.blinkProgress));
        ctx.beginPath();
        ctx.ellipse(0, 0, 7.5, eyeHeight, 0, 0, Math.PI * 2);
        ctx.fillStyle = '#ffffff';
        ctx.fill();

        if (eyeHeight > 3) {
          ctx.beginPath();
          ctx.arc(2.5, -2.5, 2.2, 0, Math.PI * 2);
          ctx.fillStyle = '#0f172a';
          ctx.fill();
        }
      }
      ctx.restore();
    };

    drawEye(-eyeSpacing);
    drawEye(eyeSpacing);

    // Cute blush cheeks
    ctx.fillStyle = 'rgba(244, 63, 94, 0.28)';
    ctx.beginPath();
    ctx.ellipse(-eyeSpacing - 6, 8 + this.currY * 0.5, 5, 2.5, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.beginPath();
    ctx.ellipse(eyeSpacing + 6, 8 + this.currY * 0.5, 5, 2.5, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.restore();
  }
}
