import { useEffect, useState } from 'react';
import Landing from './pages/Landing';
import Desk from './pages/Desk';

type Route = 'home' | 'desk';

const parse = (): Route => (window.location.hash.startsWith('#/desk') ? 'desk' : 'home');

function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(parse);
  useEffect(() => {
    const onHash = () => setRoute(parse());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  return route;
}

export default function App() {
  const route = useHashRoute();

  // 切页时回到顶部：首页较长，直接进校稿台不应停在页中
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [route]);

  return route === 'desk' ? <Desk /> : <Landing />;
}
