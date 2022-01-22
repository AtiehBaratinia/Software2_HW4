import http from 'k6/http';
import { check, group, sleep } from 'k6';

const BASE_URL = 'https://test-api.k6.io';

export const options = {
    stages: [
        { duration: '10s', target: 1000 }, // simulate ramp-up of traffic from 1 to 100 users over 5 seconds.
        { duration: '10s', target: 1000 }, // stay at 100 users for 10 seconds
        { duration: '5s', target: 0 }, // ramp-down to 0 users
      ],
    thresholds: {
      http_req_failed: ['rate<0.01'], // http errors should be less than 1%
      http_req_duration: ['p(95)<400'], // 95% of requests should be below 200ms
    },
  };

export default function() {

  const myObjects = http.get(`${BASE_URL}/public/crocodiles/`).json();
  const length = myObjects.length
  const rand = Math.floor((Math.random() * length));
  const cro_id = myObjects[rand]["id"];
  
  const obj1 = http.get(`${BASE_URL}/public/crocodiles/${cro_id}/`);
  
  check(obj1, { 'is status 200': (obj) => obj.status ===200, });

};
