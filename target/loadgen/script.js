// Steady traffic through the load balancer: ~80% list orders, ~20% create (which calls payments-svc).
import http from 'k6/http';
import { sleep } from 'k6';

export const options = { vus: 8, duration: '24h' };

export default function () {
  if (Math.random() < 0.8) {
    http.get(`http://lb:8080/orders?customer=${Math.floor(Math.random() * 200) + 1}`);
  } else {
    http.post('http://lb:8080/orders', JSON.stringify({ customer: 1 }), { headers: { 'Content-Type': 'application/json' } });
  }
  sleep(0.05);
}
