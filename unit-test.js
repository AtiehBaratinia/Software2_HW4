import http from 'k6/http';
import { check} from 'k6';

export const options = {
  stages: [
    { duration: '5s', target: 100 }, // simulate ramp-up of traffic from 1 to 100 users over 5 seconds.
    { duration: '10s', target: 100 }, // stay at 100 users for 10 seconds
    { duration: '5s', target: 0 }, // ramp-down to 0 users
  ]
};

const BASE_URL = 'https://test-api.k6.io';


export default function() {

  const myObjects = http.get(`${BASE_URL}/public/crocodiles/`);
  check(myObjects, { 'is status 200': (obj) => obj.status ===200, });
};
