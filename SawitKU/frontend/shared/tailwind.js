// Konfigurasi Tailwind (dimuat setelah tailwind CDN). Palet hijau + animasi bersama.
tailwind.config = {
  theme: { extend: {
    fontFamily: { sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'], display: ['"Bricolage Grotesque"', '"Plus Jakarta Sans"', 'system-ui', 'sans-serif'] },
    colors: { brand: { 50:'#f0f9f2',100:'#dcf1e1',200:'#bbe3c6',300:'#8ccda2',400:'#5ab37c',500:'#38995e',600:'#297b4a',700:'#22623d',800:'#1e4e33',900:'#173f2a' },
              sun: { 400:'#f7c948', 500:'#f0b429' },
              kertas: '#f6f8f2' },
    keyframes: {
      'fade-up': { '0%':{opacity:0,transform:'translateY(18px)'}, '100%':{opacity:1,transform:'none'} },
      'fade-in': { '0%':{opacity:0}, '100%':{opacity:1} },
      'pop': { '0%':{opacity:0,transform:'scale(.92)'}, '100%':{opacity:1,transform:'scale(1)'} },
      'slide-in': { '0%':{opacity:0,transform:'translateX(30px)'}, '100%':{opacity:1,transform:'none'} },
      'float': { '0%,100%':{transform:'translateY(0)'}, '50%':{transform:'translateY(-14px)'} },
      'sway': { '0%,100%':{transform:'rotate(-2deg)'}, '50%':{transform:'rotate(2deg)'} },
    },
    animation: {
      'fade-up':'fade-up .6s cubic-bezier(.2,.8,.2,1) both', 'fade-in':'fade-in .5s ease both',
      'pop':'pop .3s cubic-bezier(.2,.8,.2,1) both', 'slide-in':'slide-in .35s ease both',
      'float':'float 6s ease-in-out infinite', 'sway':'sway 5s ease-in-out infinite',
    } } }
};
