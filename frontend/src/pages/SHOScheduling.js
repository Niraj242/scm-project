import React, { useState } from 'react';
import './SHOScheduling.css';

const SHOSchedule = () => {
  const [activeTab, setActiveTab] = useState('buffer');

  // ==========================================================
  // HERE IS WHERE THE CODE GOES inside the component
  // ==========================================================
  const generateSchedule = async () => {
    try {
      // NOTE: Replace 'http://localhost:10000' with your actual backend URL later
      const response = await fetch('http://localhost:10000/api/schedule', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          target_date: "01/04/2026",
          unit_mode: "Days",
          buffers: [] // This will map to your form inputs later
        })
      });
      const data = await response.json();
      console.log("Schedule generated:", data);
      
      // Automatically switch to the schedule tab once data is received
      setActiveTab('schedule');
    } catch (error) {
      console.error("Error generating schedule:", error);
    }
  };
  // ==========================================================

  return (
    <div className="exact-container">
      <div className="tab-buttons">
        <button 
          className={activeTab === 'buffer' ? 'active-tab' : ''} 
          onClick={() => setActiveTab('buffer')}
        >
          Buffer Input Grid (Image 1)
        </button>
        
        {/* I also added a button here to actually trigger the function you just pasted! */}
        <button 
           style={{ backgroundColor: '#28a745', color: 'white', fontWeight: 'bold', border: '1px solid #218838' }}
           onClick={generateSchedule}
        >
          Generate Schedule 
        </button>

        <button 
          className={activeTab === 'schedule' ? 'active-tab' : ''} 
          onClick={() => setActiveTab('schedule')}
        >
          Schedule Output (Image 2)
        </button>
      </div>

      {activeTab === 'buffer' && (
        <div className="scroll-wrapper">
          <table className="exact-buffer-table">
            <thead>
              <tr>
                <th className="row-header"></th>
                <th colSpan="2" className="bg-cyan">CH 01</th>
                <th colSpan="2">CH 02</th>
                <th colSpan="2">CH 03</th>
                <th colSpan="2">CH 04</th>
                <th colSpan="2">CH 05</th>
                <th colSpan="2">XIJI</th>
                <th colSpan="2">CH 07</th>
                <th colSpan="2">CH 08</th>
                <th colSpan="2" className="bg-cyan">CH 11</th>
              </tr>
              <tr>
                <th className="row-header font-bold">PART</th>
                <th>IR</th><th>OR</th>
                <th>IR</th><th>OR</th>
                <th>IR</th><th>OR</th>
                <th>IR</th><th>OR</th>
                <th>IR</th><th>OR</th>
                <th>IR</th><th>OR</th>
                <th>IR</th><th>OR</th>
                <th>IR</th><th>OR</th>
                <th>IR</th><th>OR</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="font-bold">Running</td>
                <td>1.2</td><td>0.3</td>
                <td>0.1</td><td>0.5</td>
                <td>1.7</td><td>0.7</td>
                <td>0.1</td><td>1</td>
                <td>1.2</td><td>0.1</td>
                <td>0</td><td>0</td>
                <td></td><td></td>
                <td>0.6</td><td>0.6</td>
                <td>0.8</td><td>0.8</td>
              </tr>
              <tr>
                <td className="font-bold">Next Type</td>
                <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
              </tr>
              <tr>
                <td className="font-bold">Expected Time</td>
                <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
              </tr>
              {/* OD Buffer Blocks */}
              <tr>
                <td rowSpan="3" className="font-bold">OD Buffer</td>
                <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
              </tr>
              <tr>
                <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td className="border-bottom-thick">0.2</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td className="border-bottom-thick">0.2</td>
              </tr>
              <tr>
                <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td className="font-bold">6311</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td className="font-bold">63/28</td>
              </tr>
              {/* Face Buffer Blocks */}
              <tr>
                <td rowSpan="3" className="font-bold">Face Buffer</td>
                <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
              </tr>
              <tr>
                <td></td><td className="border-bottom-thick">1</td><td></td><td></td><td></td><td className="border-bottom-thick">0.1</td><td></td><td></td><td></td><td className="border-bottom-thick">0.8</td><td></td><td></td><td></td><td></td><td className="border-bottom-thick">1</td><td className="border-bottom-thick">1.1</td><td></td><td></td>
              </tr>
              <tr>
                <td></td><td className="font-bold">63/28</td><td></td><td></td><td></td><td className="font-bold">6306</td><td></td><td></td><td></td><td className="font-bold">6311</td><td></td><td></td><td></td><td></td><td className="font-bold">6307</td><td className="font-bold">6307</td><td></td><td></td>
              </tr>
              {/* HT Buffer Blocks */}
              <tr>
                <td rowSpan="4" className="font-bold">HT Buffer</td>
                <td></td><td></td><td className="border-bottom-thick font-bold">0.4</td><td></td><td className="border-bottom-thick font-bold">0.7</td><td className="border-bottom-thick font-bold">1.7</td><td className="border-bottom-thick font-bold">2</td><td className="border-bottom-thick font-bold">1</td><td className="border-bottom-thick font-bold">1.3</td><td></td><td></td><td></td><td></td><td></td><td className="border-bottom-thick font-bold">1.7</td><td className="border-bottom-thick font-bold">1.7</td><td></td><td></td>
              </tr>
              <tr>
                <td></td><td></td><td className="font-bold">6007</td><td></td><td className="font-bold">6306</td><td className="font-bold">6306</td><td className="font-bold">6010</td><td className="font-bold">6010</td><td className="font-bold">6311</td><td className="font-bold">6311</td><td></td><td></td><td></td><td></td><td className="font-bold">6307</td><td className="font-bold">6307</td><td></td><td></td>
              </tr>
              <tr>
                <td className="border-bottom-thick font-bold">1.2</td><td className="border-bottom-thick font-bold">1.2</td><td className="border-bottom-thick font-bold">0.4</td><td className="border-bottom-thick font-bold">1.3</td><td className="border-bottom-thick font-bold">0.7</td><td className="border-bottom-thick font-bold">0.6</td><td></td><td></td><td className="border-bottom-thick font-bold">1</td><td></td><td></td><td></td><td></td><td></td><td></td><td className="border-bottom-thick font-bold">0.3</td><td className="border-bottom-thick font-bold">1</td><td className="border-bottom-thick font-bold">1.2</td>
              </tr>
              <tr>
                <td className="font-bold">63/28</td><td className="font-bold">63/28</td><td className="font-bold">6007 RE</td><td className="font-bold">6007 RE</td><td className="font-bold">6306 CN</td><td className="font-bold">6306 VU</td><td></td><td></td><td className="font-bold">6312</td><td></td><td></td><td></td><td></td><td></td><td></td><td className="font-bold">6307N</td><td className="font-bold">63/28</td><td className="font-bold">63/28</td>
              </tr>
              <tr>
                <td className="font-bold">Running Types</td>
                <td className="font-bold">63/28</td><td className="font-bold">63/28</td><td className="font-bold">6007</td><td className="font-bold">6007</td><td className="font-bold">6306</td><td className="font-bold">6306</td><td className="font-bold">6308</td><td className="font-bold">6308</td><td className="font-bold">6311</td><td className="font-bold">6311</td><td className="font-bold">23102RS</td><td className="font-bold">2310 2RS</td><td></td><td></td><td className="font-bold">6307</td><td className="font-bold">6307</td><td className="font-bold">63/28</td><td className="font-bold">63/28</td>
              </tr>
              <tr>
                <td className="font-bold">Next Type</td>
                <td></td><td></td><td></td><td></td><td></td><td></td><td></td><td className="font-bold">6010</td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
              </tr>
              {/* Calculated Results Row */}
              <tr>
                <td className="font-bold">Buffer in day</td>
                <td className="font-bold">2.4</td><td className="font-bold text-red">2.5</td><td className="font-bold text-red">0.9</td><td className="font-bold text-red">1.8</td><td className="font-bold">3.1</td><td className="font-bold">3.1</td><td className="font-bold">2.1</td><td className="font-bold">2</td><td className="font-bold">3.5</td><td className="font-bold text-red">1.1</td><td className="font-bold text-red">0</td><td className="font-bold text-red">0</td><td className="font-bold text-red">0</td><td className="font-bold text-red">0</td><td className="font-bold">3.3</td><td className="font-bold text-red">3.7</td><td className="font-bold text-red">1.8</td><td className="font-bold text-red">2.2</td>
              </tr>
              <tr>
                <td className="font-bold">RUSH Batches</td>
                <td></td><td className="bg-red text-white font-bold text-xs">NO NEXT MAT</td><td className="bg-red text-white font-bold text-xs">NO NEXT MAT</td><td className="bg-red text-white font-bold text-xs">NO NEXT MAT</td><td></td><td></td><td></td><td></td><td></td><td className="bg-red text-white font-bold text-xs">NO NEXT MAT</td><td className="bg-red text-white font-bold text-xs">NO NEXT MAT</td><td className="bg-red text-white font-bold text-xs">NO NEXT MAT</td><td className="bg-red text-white font-bold text-xs">NO NEXT MAT</td><td className="bg-red text-white font-bold text-xs">NO NEXT MAT</td><td></td><td></td><td className="bg-red text-white font-bold text-xs">NO NEXT MAT</td><td className="bg-red text-white font-bold text-xs">NO NEXT MAT</td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'schedule' && (
        <div className="schedule-layout">
          <div className="schedule-header">
            <h2 className="text-blue">Face & OD Grinding Schedule</h2>
            <h2 className="text-blue">Date :- 01/04/2026</h2>
          </div>

          <div className="three-columns">
            {/* COLUMN 1: FACE GRINDING */}
            <div className="column column-face">
              <h3 className="column-title text-blue">Face Grinding</h3>
              <table className="schedule-table">
                <thead>
                  <tr>
                    <th className="bg-light-blue text-blue" style={{width: '60%'}}>DDS (544)</th>
                    <th className="bg-light-blue text-blue">STD BOX</th>
                    <th colSpan="2" className="bg-white">Shift Priority<br/><span className="text-blue">2nd</span> | <span className="text-blue">3rd</span></th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td className="font-bold text-red">BREAKDOWN DAY 03</td><td>0</td><td rowSpan="4">1</td><td rowSpan="4">P2</td></tr>
                  <tr><td className="font-bold">33005---OR</td><td>0</td></tr>
                  <tr><td className="font-bold">33005---IR</td><td>0</td></tr>
                  <tr><td>BT11366---IR BLUE BOX</td><td>0</td></tr>
                  <tr><td className="text-red">BTH1024---IR APQ</td><td>0</td><td rowSpan="2">3</td><td rowSpan="2"></td></tr>
                  <tr><td></td><td>0</td></tr>
                  
                  {/* Gardner (1016) */}
                  <tr>
                    <th className="bg-light-blue text-blue">Gardner ( 1016 + USA 1996 )</th>
                    <th className="bg-light-blue text-blue">STD BOX</th>
                    <th colSpan="2"></th>
                  </tr>
                  <tr><td>6306---OR</td><td>0</td><td rowSpan="2">1</td><td rowSpan="6">P1</td></tr>
                  <tr><td className="text-red font-bold">6311---OR APQ</td><td>0</td></tr>
                  <tr><td>2820---OR</td><td>0</td><td rowSpan="4">2</td></tr>
                  <tr><td>32212---OR</td><td>0</td></tr>
                  <tr><td>6307---OR</td><td>0</td></tr>
                  <tr><td>BT11366---OR</td><td>0</td></tr>
                  <tr><td className="text-red font-bold">6312---OR APQ</td><td>0</td><td>3</td><td></td></tr>
                  
                  {/* DDS Cell */}
                  <tr>
                    <th className="bg-light-blue text-blue">DDS Cell ( 709 + 1186 )</th>
                    <th className="bg-light-blue text-blue">STD BOX</th>
                    <th colSpan="2"></th>
                  </tr>
                  <tr><td className="font-bold text-red">BAR0594---IR</td><td></td><td>1</td><td rowSpan="7">P1</td></tr>
                  <tr><td>32212---IR</td><td></td><td rowSpan="5">2</td></tr>
                  <tr><td>BT11798---OR</td><td></td></tr>
                  <tr><td>BT11798---IR</td><td></td></tr>
                  <tr><td>3525---OR</td><td></td></tr>
                  <tr><td>3585---IR</td><td></td></tr>
                  <tr><td>32217---OR</td><td></td><td rowSpan="3">3</td></tr>
                  <tr><td>32217---IR</td><td></td><td rowSpan="2"></td></tr>
                  <tr><td className="font-bold text-red">BAR0594---IR</td><td></td></tr>
                </tbody>
              </table>
            </div>

            {/* COLUMN 2: OD GRINDING */}
            <div className="column column-od">
              <h3 className="column-title text-blue">OD Grinding</h3>
              <table className="schedule-table">
                <thead>
                  <tr>
                    <th className="bg-light-blue text-blue" style={{width: '60%'}}>CL -46 Cell 2 ( 0945 + 0839 )</th>
                    <th className="bg-light-blue text-blue">STD BOX</th>
                    <th colSpan="2" className="bg-white">Shift Priority<br/><span className="text-blue">2nd</span> | <span className="text-blue">3rd</span></th>
                  </tr>
                </thead>
                <tbody>
                  <tr><td className="font-bold">6306-OR <span className="text-red">TOTE BOX</span>(+2TO-6)</td><td></td><td>1</td><td rowSpan="4">P1</td></tr>
                  <tr><td>2820---OR</td><td></td><td rowSpan="2">2</td></tr>
                  <tr><td>6307---OR BLUE BOX</td><td></td></tr>
                  <tr><td>BT11366---OR BLUE BOX</td><td></td><td>3</td></tr>
                  
                  {/* Cell 1 */}
                  <tr>
                    <th className="bg-light-blue text-blue">CL-46 Cell 1 ( 0661 + 1125 )</th>
                    <th className="bg-light-blue text-blue">STD BOX</th>
                    <th colSpan="2"></th>
                  </tr>
                  <tr><td>6311---OR</td><td></td><td rowSpan="2">1</td><td rowSpan="5">P1</td></tr>
                  <tr><td>32212---OR</td><td></td></tr>
                  <tr><td>3525---OR</td><td></td><td rowSpan="2">2</td></tr>
                  <tr><td>32217---OR</td><td></td></tr>
                  <tr><td>BT10230---OR</td><td></td><td>3</td></tr>
                  
                  {/* Cell 3 */}
                  <tr>
                    <th className="bg-light-blue text-blue">CL-46 Cell 3 ( 1600 + 1903 )</th>
                    <th className="bg-light-blue text-blue">STD BOX</th>
                    <th colSpan="2"></th>
                  </tr>
                  <tr><td>6307---OR BLUE BOX</td><td></td><td rowSpan="2">1</td><td rowSpan="4">P1</td></tr>
                  <tr><td>BT11798---OR</td><td></td></tr>
                  <tr><td>BAH0303---OR</td><td></td><td rowSpan="2">2</td></tr>
                  <tr><td className="font-bold">6306-OR+ VU <span className="text-red">TOTE BOX</span></td><td></td></tr>

                  {/* Cell 4 */}
                  <tr>
                    <th className="bg-light-blue text-blue">CL-46 Cell 4 ( 170 + 1904 )</th>
                    <th className="bg-light-blue text-blue">STD BOX</th>
                    <th colSpan="2"></th>
                  </tr>
                  <tr><td>BTH329129---OR BLUE BOX</td><td></td><td>1</td><td rowSpan="3">P1</td></tr>
                  <tr><td className="font-bold text-red">BAH0381-OR BLUE BOX</td><td></td><td>2</td></tr>
                  <tr><td>BTH329129---OR BLUE BOX</td><td></td><td>3</td></tr>
                </tbody>
              </table>
            </div>

            {/* COLUMN 3: HEAT TREATMENT */}
            <div className="column column-ht">
               <table className="schedule-table ht-table">
                <thead>
                  <tr>
                    <th colSpan="3" className="bg-light-blue text-blue">HEAT TREATMENT</th>
                    <th colSpan="2" className="bg-light-blue text-blue">DATE - 01/04/2026</th>
                  </tr>
                </thead>
                <tbody>
                  {/* AICHELIN */}
                  <tr>
                    <th className="bg-light-blue text-blue text-left">AICHELIN.(896)</th>
                    <th className="bg-light-blue text-blue">QTY</th>
                    <th className="bg-light-blue text-blue">Cha 350</th>
                    <th className="bg-light-blue text-blue text-left">ASTLINK FURNACE( 1018)</th>
                    <th className="bg-light-blue text-blue">QTY</th>
                  </tr>
                  <tr>
                    <td>72487---OR</td><td></td><td>T3</td>
                    <td>BT11366---OR</td><td></td>
                  </tr>
                  <tr>
                    <td>32212---IR</td><td>6000</td><td>T5</td>
                    <td>63/28---OR</td><td>12000</td>
                  </tr>
                  <tr>
                    <td>3720---OR</td><td>5000</td><td>T6</td>
                    <td>33108---OR</td><td></td>
                  </tr>
                  <tr>
                    <td>72212---IR</td><td></td><td>T3</td>
                    <td><span className="font-bold">6007---OR <span className="text-red">RE S0</span></span></td><td></td>
                  </tr>
                  
                  {/* ROLLER FURNACE */}
                  <tr>
                    <th className="bg-light-blue text-blue text-left mt-row">ROLLER FURNACE ( 148 )</th>
                    <th className="bg-light-blue text-blue mt-row">QTY</th>
                    <th className="bg-light-blue text-blue mt-row">Cha 250</th>
                    <th className="bg-light-blue text-blue text-left mt-row">MPLICITY FURNACE(1238)</th>
                    <th className="bg-light-blue text-blue mt-row">QTY</th>
                  </tr>
                  <tr>
                    <td>BAR0594---IR</td><td>10000</td><td>HUB3</td>
                    <td>1922---OR</td><td>15000</td>
                  </tr>
                  <tr>
                    <td><span className="font-bold">32007<span className="text-red">VB</span>---IR BLUE BOX</span></td><td></td><td>T8</td>
                    <td><span className="font-bold">63/28---IR <span className="text-red">TOTE BOX</span></span></td><td>15000</td>
                  </tr>
                  <tr>
                    <td>63/28---IR BLUE BOX</td><td>12000</td><td>CH11</td>
                    <td>1988---IR</td><td></td>
                  </tr>

                  {/* REMARK BOX */}
                  <tr>
                    <th colSpan="2" className="bg-dark-blue text-white mt-row">REMARK / CONVERSION QTY</th>
                    <th className="bg-dark-blue text-white mt-row"></th>
                    <th className="bg-dark-blue text-white text-center mt-row">FOR FACE &OD</th>
                    <th className="bg-dark-blue text-white mt-row">QTY</th>
                  </tr>
                  <tr>
                    <td colSpan="2">6010 OR</td><td></td><td>BTH1024 OR</td><td>2800</td>
                  </tr>
                  <tr>
                    <td colSpan="2">6206 IR OR</td><td></td><td>6311 OR</td><td></td>
                  </tr>
                  <tr>
                    <td colSpan="2">6007 IR RE</td><td></td><td>BAH0381 OR-10K IR- 12K</td><td></td>
                  </tr>
                  <tr>
                    <td colSpan="2" className="font-bold">BTH1024 IR</td><td className="font-bold">8000</td><td>BTH329129 IR</td><td>7000</td>
                  </tr>
                </tbody>
              </table>

              {/* HIGH ALERT BOX */}
              <div className="alert-box">
                <div className="alert-header">HIGH ALERT TYPE</div>
                <div className="alert-item font-bold text-red">63/28 OR = VKR SIZE</div>
                <div className="alert-item font-bold text-red">BAH0378OR= VKR+ SIZE+ CLA</div>
                <div className="alert-item font-bold text-red">BAH0348 OR= VKR+CLA + SIZE</div>
                <div className="alert-item font-bold text-red">BAH0381 OR= VKR+ CLA</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SHOSchedule;
