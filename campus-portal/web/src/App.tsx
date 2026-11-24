import { useEffect, useState } from 'react';
import Landing from './pages/Landing';
import Desk from './pages/Desk';
import Assistant from './pages/Assistant';
import Compose from './pages/Compose';

type Route = 'home' | 'desk' | 'assistant' | 'compose';

const parse = (): Route => {
  if (window.location.hash.startsWith('#/desk')) return 'desk';
  if (window.location.hash.startsWith('#/assistant')) return 'assistant';
  if (window.location.hash.startsWith('#/compose')) return 'compose';
  return 'home';
};

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

  if (route === 'desk') return <Desk />;
  if (route === 'assistant') return <Assistant />;
  if (route === 'compose') return <Compose />;
  return <Landing />;
}
