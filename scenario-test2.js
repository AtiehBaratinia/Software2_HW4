
import { check} from 'k6';
import {randomItem } from "https://jslib.k6.io/k6-utils/1.1.0/index.js";
import { Httpx} from 'https://jslib.k6.io/httpx/0.0.2/index.js';


let session = new Httpx({baseURL: 'https://test-api.k6.io'});

const USERNAME = 'hanieeeeeh';
const PASSWORD = 'hanieh';
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
    
    const loginRes = session.post(`/auth/token/login/`, {
      username: USERNAME,
      password: PASSWORD,
    });
  
    check(loginRes, {
      'logged in successfully': (resp) => resp.json('access') !== '',
    });

    let authToken = loginRes.json('access');
    session.addHeader('Authorization', `Bearer ${authToken}`);
    

    const myObjects = session.get(`/my/crocodiles/`).json();
    check(myObjects, { 'retrieved crocodiles': (obj) => obj.length > 0 });
    
    
    for (let i = 0;i < 2;i++){
        let croc = {
            name: `Crocy ${i}`,
            sex: randomItem(["M", "F"]),
            date_of_birth: '2020-01-01',
        };
        let insert = session.post(`/my/crocodiles/`, croc);
        check(insert, {'is status 201': (obj) => obj.status ===201,});
    
    }

  };

