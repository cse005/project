// Function to generate slow, organic, generic floating circles on a canvas.
function initFloatingParticles() {
    const canvas = document.getElementById('floating-canvas');
    const ctx = canvas.getContext('2d');

    let particlesArray = [];
    let numberOfParticles = 75; // Adjust density of generic circles

    // Function to set canvas to generic full screen dimensions on load/resize
    function setGenericCanvasSize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    setGenericCanvasSize();
    window.addEventListener('resize', setGenericCanvasSize);

    // Particle object blueprint with generic floating motion properties
    class Particle {
        constructor() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.size = Math.random() * 10 + 2; // Generic circle size range
            this.speedX = (Math.random() * 0.3) - 0.15; // Slow vertical drift speed
            this.speedY = (Math.random() * 0.3) - 0.15; // Slow horizontal drift speed
            // Generic color range: soft white, slight gold tint, soft green tint
            let colorIndex = Math.floor(Math.random() * 3);
            if (colorIndex == 0) this.color = 'rgba(255, 255, 255, 0.4)'; // soft white
            if (colorIndex == 1) this.color = 'rgba(230, 184, 0, 0.15)'; // slight gold
            if (colorIndex == 2) this.color = 'rgba(10, 46, 28, 0.4)'; // soft green-ish
        }

        update() {
            // Update generic particle position
            this.x += this.speedX;
            this.y += this.speedY;

            // Bounce particles off the generic edges of the screen
            if (this.x > canvas.width || this.x < 0) this.speedX = -this.speedX;
            if (this.y > canvas.height || this.y < 0) this.speedY = -this.speedY;
        }

        draw() {
            // Drawing the generic circle particle
            ctx.fillStyle = this.color;
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.random() * 2 * Math.PI);
            ctx.fill();
        }
    }

    // Generic animation loop for particles
    function animateParticles() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        for (let i = 0; i < particlesArray.length; i++) {
            particlesArray[i].update();
            particlesArray[i].draw();
        }
        requestAnimationFrame(animateParticles);
    }

    // Initialize all generic particle objects on screen
    for (let i = 0; i < numberOfParticles; i++) {
        particlesArray.push(new Particle());
    }

    animateParticles();
}

// Fire the generic initialization after page is loaded
window.addEventListener('load', initFloatingParticles);