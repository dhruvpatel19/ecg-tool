/* Shared helpers for the ECG learning-mode mocks: ECG strip generators + chat utils.
   Mocks are illustrative — strips are stylized gestalts, not real signals. */
(function(global){
  function g(t,c,a,w){return a*Math.exp(-((t-c)*(t-c))/(2*w*w));}
  // Single-lead rhythm-strip y-value generators (baseline 60, "up" = smaller y).
  var GEN={
    sinus:function(x){var t=x%86;return 60+g(t,16,-7,5)+g(t,40,5,2)+g(t,44,-34,2.4)+g(t,48,20,2.4)+g(t,66,-12,7);},
    brady:function(x){var t=x%150;return 60+g(t,20,-7,6)+g(t,52,-34,2.6)+g(t,58,18,2.6)+g(t,86,-12,8);},
    sinus_tach:function(x){var t=x%52;return 60+g(t,8,-6,3)+g(t,22,-32,2)+g(t,26,16,2)+g(t,40,-9,5);},
    afib:function(x){var t=x%70;var f=2.5*Math.sin(x/3.1)+1.8*Math.sin(x/1.7);return 60+f+g(t,30,-30,2.4)+g(t,34,16,2.4)+g(t,52,-9,6);},
    flutter:function(x){var saw=((x%18)/18)*14-7;var t=x%108;return 60+saw+g(t,40,-26,2.6)+g(t,44,14,2.6);},
    svt:function(x){var t=x%40;return 60+g(t,12,-30,2)+g(t,16,15,2)+g(t,30,-8,5);},
    vt:function(x){var t=x%46;return 60+g(t,12,-40,7)+g(t,30,30,8);},
    chb:function(x){return 60+g(x%56,10,-7,4)+g(x%150,34,-34,6)+g(x%150,50,20,7);}, // P's march independent of slow wide QRS
    first_degree:function(x){var t=x%92;return 60+g(t,10,-7,4)+g(t,40,-32,2.4)+g(t,44,18,2.4)+g(t,64,-11,7);}, // long PR
    paced:function(x){var t=x%92;var spk=(t>30&&t<32)?-26:0;return 60+spk+g(t,12,0,1)+g(t,44,-30,5)+g(t,52,16,6)+g(t,72,12,8);} // spike + wide paced QRS
  };
  function pointsFor(kind,w){var fn=GEN[kind]||GEN.sinus;var p=[];for(var x=0;x<=(w||640);x+=2){p.push(x+","+fn(x).toFixed(1));}return p.join(" ");}
  function strip(kind,opts){opts=opts||{};var w=opts.w||640,h=opts.h||120;
    return '<svg viewBox="0 0 '+w+' '+h+'" role="img" aria-label="ECG strip '+kind+'">'+
      '<g stroke="var(--grid)" stroke-width="0.6"><line x1="0" y1="30" x2="'+w+'" y2="30"/><line x1="0" y1="60" x2="'+w+'" y2="60"/><line x1="0" y1="90" x2="'+w+'" y2="90"/></g>'+
      '<polyline points="'+pointsFor(kind,w)+'" fill="none" stroke="var(--trace)" stroke-width="1.7" stroke-linejoin="round"/></svg>';}
  // tiny chat helpers bound to a container element
  function chat(box){
    return {
      ai:function(html){var d=document.createElement('div');d.className='msg ai';d.innerHTML='<span class="who">AI tutor</span><div class="body">'+html+'</div>';box.appendChild(d);box.scrollTop=box.scrollHeight;return d;},
      you:function(t){var d=document.createElement('div');d.className='msg you';d.innerHTML='<span class="who">You</span><div class="body">'+t+'</div>';box.appendChild(d);box.scrollTop=box.scrollHeight;},
      choices:function(opts){var wdiv=document.createElement('div');wdiv.className='row';wdiv.style.marginTop='2px';opts.forEach(function(o){var b=document.createElement('button');if(o.cls)b.className=o.cls;b.innerHTML=o.label;b.onclick=function(){wdiv.remove();if(o.say)this_you(o.say);o.go();};b.onclick=(function(o,wdiv){return function(){wdiv.remove();o.go();};})(o,wdiv);wdiv.appendChild(b);});box.appendChild(wdiv);box.scrollTop=box.scrollHeight;return wdiv;}
    };
  }
  global.ECG={strip:strip,points:pointsFor,gauss:g,GEN:GEN,chat:chat};
})(window);
