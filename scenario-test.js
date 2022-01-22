
import { check} from 'k6';
import {randomItem } from "https://jslib.k6.io/k6-utils/1.1.0/index.js";
import { Httpx} from 'https://jslib.k6.io/httpx/0.0.2/index.js';
import http from 'k6/http';

let session = new Httpx({baseURL: 'https://test-api.k6.io'});

const USERNAME = 'hanieeeeeh';
const PASSWORD = 'hanieh';
export const options = {
    
    thresholds: {
        http_req_failed: ['rate<0.01'], // http errors should be less than 1%
        http_req_duration: ['p(90)<800'], // 95% of requests should be below 200ms
    },
    scenarios:{
        
        scenario1:{
            executor: 'shared-iterations',
            exec: "func1",
            vus: 100,
            iterations: 100,
            maxDuration: '10s',
            
        }, 
        scenario2:{
            vus: 100,
            maxDuration: '10s',
            executor: 'shared-iterations',
            exec: "func2",
            iterations: 100,
            
        }
    }
    
};



export function func2() {
    
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
    
    if(myObjects.length < 10){
        let croc = {
            name: `Crocy ${i}`,
            sex: randomItem(["M", "F"]),
            date_of_birth: '2020-01-01',
        };
        let insert = session.post(`/my/crocodiles/`, croc);
        check(insert, {'is status 201': (obj) => obj.status ===201,});
    }
    
  };

  
const BASE_URL = 'https://test-api.k6.io';
export function func1(){
    const myObjects = http.get(`${BASE_URL}/public/crocodiles/`).json();
    const length = myObjects.length
    const rand = Math.floor((Math.random() * length));
    const cro_id = myObjects[rand]["id"];
    
    const obj1 = http.get(`${BASE_URL}/public/crocodiles/${cro_id}/`);
    
    check(obj1, { 'is status 200': (obj) => obj.status ===200, });
  
};