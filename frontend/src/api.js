import axios from 'axios';

export const api = axios.create({ baseURL: '/api', withCredentials: true });

api.interceptors.response.use(
  (response) => {
    if (response.config.url !== '/health') {
      sessionStorage.removeItem('d5macro-auth-reload');
    }
    return response;
  },
  (error) => {
    if (error.response?.status === 401 && !sessionStorage.getItem('d5macro-auth-reload')) {
      sessionStorage.setItem('d5macro-auth-reload', '1');
      window.location.replace(`/?refresh=${Date.now()}`);
    }
    return Promise.reject(error);
  },
);

export const websocketUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
};
