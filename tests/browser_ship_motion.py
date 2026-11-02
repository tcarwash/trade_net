"""Run: uv run --with playwright python tests/browser_ship_motion.py."""
import unittest

from browser_smoke import CockpitBrowserTests


class ShipMotionBrowserTests(CockpitBrowserTests):
    def test_ship_motion_matches_elapsed_time_across_redraws(self):
        result = self.page.evaluate("""async () => {
          busy=true; // Keep periodic refresh from replacing the browser fixture.
          const canvas=svg('svg',{width:800,height:500,viewBox:'0 0 800 500'});
          document.body.append(canvas);
          canvas.setCurrentTime(40); // The map has been open before this flight.
          const ship={...state.game.ship,id:'motion-regression',name:'Motion check'};
          const start=Date.now()/1000-5, samples=[];
          for(let i=0;i<5;i++){
            canvas.replaceChildren();
            shipGlyph(canvas,0,0,ship.name,null,ship,{from:{x:0,y:100},to:{x:400,y:100},elapsed:Date.now()/1000-start,duration:20});
            await new Promise(requestAnimationFrame);
            await new Promise(requestAnimationFrame);
            const matrix=canvas.querySelector('.ship-marker').getCTM();
            samples.push({x:matrix.e,y:matrix.f,expected:(Date.now()/1000-start)*20});
            await new Promise(resolve=>setTimeout(resolve,150));
          }
          canvas.remove();return samples;
        }""")
        for sample in result:
            self.assertAlmostEqual(sample['x'], sample['expected'], delta=1.5)
            self.assertAlmostEqual(sample['y'], 100, delta=.01)
        self.assertGreater(result[-1]['x'], result[0]['x'] + 10)

    def test_orbit_tracks_its_phase_across_redraws(self):
        result = self.page.evaluate("""async () => {
          busy=true;
          const canvas=svg('svg',{width:800,height:500,viewBox:'0 0 800 500'});
          document.body.append(canvas);canvas.setCurrentTime(40);
          const ship={...state.game.ship,id:'orbit-regression',name:'Orbit check'},samples=[];
          const pathData='M 60 0 A 60 40 0 1 1 -60 0 A 60 40 0 1 1 60 0';
          for(let i=0;i<5;i++){
            canvas.replaceChildren();canvas.setCurrentTime(40+i*7);
            const layer=svg('g',{});canvas.append(layer);
            orbitalShipGlyph(layer,{x:200,y:200},ship,60,40,pathData,canvas);
            await new Promise(requestAnimationFrame);
            await new Promise(requestAnimationFrame);
            const motion=layer.querySelector('animateMotion'),icon=motion.parentNode;
            const elapsed=canvas.getCurrentTime()-parseFloat(motion.getAttribute('begin'));
            const phase=(elapsed/parseFloat(motion.getAttribute('dur')))%1;
            const track=svg('path',{d:pathData});canvas.append(track);
            const expected=track.getPointAtLength(track.getTotalLength()*phase),matrix=icon.getCTM();
            samples.push({error:Math.hypot(matrix.e-200-expected.x,matrix.f-200-expected.y),x:matrix.e,y:matrix.f});
            await new Promise(resolve=>setTimeout(resolve,150));
          }
          canvas.remove();return samples;
        }""")
        for sample in result:
            self.assertLess(sample['error'], 1.5)
        for before, after in zip(result, result[1:]):
            # Aging the SVG root must not change the ship's orbital phase.
            self.assertLess(((after['x']-before['x'])**2+(after['y']-before['y'])**2)**.5, 8)


if __name__ == '__main__':
    unittest.main(defaultTest=[
        'ShipMotionBrowserTests.test_ship_motion_matches_elapsed_time_across_redraws',
        'ShipMotionBrowserTests.test_orbit_tracks_its_phase_across_redraws',
    ])
