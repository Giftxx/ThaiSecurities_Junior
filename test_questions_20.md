# 20 Test Questions & Expected Answers — Manual Web UI Testing

> **หมายเหตุ:** คำถามเหล่านี้ไม่ซ้ำกับตัวอย่างใน README  
> ใช้ทดสอบบนหน้าเว็บ http://localhost:8000/ui/index.html  
> คำตอบที่ได้อาจมีรายละเอียดมากกว่าหรือน้อยกว่า "Expected Answer"  
> ให้ดูว่า **ข้อมูลหลักตรงกัน** หรือไม่

---

## Stock Recommendations (คำแนะนำหุ้น)

### Q1: ราคาเป้าหมายของหุ้น BBL เท่าไหร่?
**Expected Answer:** ราคาเป้าหมาย (Target Price) ของ BBL คือ **THB 185.00** โดยมีระดับ upside +13.8% จากราคาปัจจุบัน THB 162.50  
**Namespace:** stock_recommendations

### Q2: DELTA มี Dividend Yield ปี 2026E เท่าไหร่?
**Expected Answer:** DELTA มี Dividend Yield ปี 2026E อยู่ที่ **1.2%**  
**Namespace:** stock_recommendations

### Q3: หุ้นตัวไหนได้รับคำแนะนำ HOLD?
**Expected Answer:** **KBANK** (Kasikornbank) ได้รับคำแนะนำ HOLD ที่ราคาเป้าหมาย THB 155.00  
**Namespace:** stock_recommendations

### Q4: EPS ปี 2026E ของ PTT เท่าไหร่?
**Expected Answer:** EPS ปี 2026E ของ PTT คือ **THB 4.05**  
**Namespace:** stock_recommendations

### Q5: DELTA มีรายได้จาก Datacenter กี่เปอร์เซ็นต์?
**Expected Answer:** DELTA มีรายได้จาก Datacenter Power คิดเป็น **45%** ของรายได้ทั้งหมด โดยเติบโต 30% YoY  
**Namespace:** stock_recommendations

### Q6: ใครเป็นนักวิเคราะห์ที่ออกรายงานหุ้น BBL?
**Expected Answer:** **Napaporn Srisawat** เป็นนักวิเคราะห์ที่ออกรายงานหุ้น BBL  
**Namespace:** stock_recommendations

### Q7: NPL Ratio ของ BBL ปี 2026E อยู่ที่เท่าไหร่?
**Expected Answer:** NPL Ratio ของ BBL ปี 2026E คาดว่าจะอยู่ที่ **2.8%** (ดีขึ้นจาก 3.2% ในปี 2024A)  
**Namespace:** stock_recommendations

---

## Market Reports (รายงานตลาด)

### Q8: SET Index วันที่ 11 มีนาคม 2026 ปิดที่เท่าไหร่?
**Expected Answer:** SET Index ปิดที่ **1,438.92 จุด** เพิ่มขึ้น 13.25 จุด (+0.93%)  
**Namespace:** market_reports

### Q9: นักลงทุนต่างชาติซื้อสุทธิเท่าไหร่ในวันที่ 10 มีนาคม 2026?
**Expected Answer:** นักลงทุนต่างชาติซื้อสุทธิ **THB 2.1 billion** ในวันที่ 10 มีนาคม 2026  
**Namespace:** market_reports

### Q10: หุ้น Top Gainers วันที่ 10 มีนาคม 2026 มีอะไรบ้าง?
**Expected Answer:** Top Gainers:
1. **DELTA** - THB 892.00 (+5.2%) - Strong export orders
2. **GULF** - THB 52.75 (+4.1%) - New power plant approval
3. **AOT** - THB 68.50 (+3.8%) - Tourism recovery data  
**Namespace:** market_reports

### Q11: CPI เดือนกุมภาพันธ์ 2026 เพิ่มขึ้นเท่าไหร่?
**Expected Answer:** CPI เดือนกุมภาพันธ์ 2026 เพิ่มขึ้น **+1.8% YoY** (ต่ำกว่าที่คาดการณ์ไว้ที่ +2.1%)  
**Namespace:** market_reports

### Q12: มูลค่าการซื้อขายวันที่ 11 มีนาคม 2026 เท่าไหร่?
**Expected Answer:** มูลค่าการซื้อขาย **THB 62.5 billion**  
**Namespace:** market_reports

---

## Regulations (กฎระเบียบ)

### Q13: ตลาดหุ้นไทยมี Circuit Breaker อย่างไร?
**Expected Answer:** Market-Wide Circuit Breaker:
- SET Index ลดลง **8%** → หยุดซื้อขาย 30 นาที
- SET Index ลดลง **15%** → หยุดซื้อขาย 1 ชั่วโมง
- SET Index ลดลง **20%** → หยุดซื้อขายทั้งวัน  
**Namespace:** regulations

### Q14: การ Settlement ของ SET ใช้ระบบอะไร?
**Expected Answer:** ใช้ระบบ **T+2** (Settlement Cycle) สกุลเงินบาท (THB) ผ่าน Thailand Clearing House (TCH)  
**Namespace:** regulations

### Q15: Tick Size ของหุ้นราคา 150 บาท คือเท่าไหร่?
**Expected Answer:** หุ้นราคา 150 บาท อยู่ในช่วง 100-200 บาท มี Tick Size = **THB 1.00**  
**Namespace:** regulations

### Q16: Board Lot ของตลาดหุ้นไทยคือเท่าไหร่?
**Expected Answer:** Board Lot = **100 หุ้น** (Odd Lot คือ < 100 หุ้น ซื้อขายบน Odd-Lot Board)  
**Namespace:** regulations

---

## Company Profiles (โปรไฟล์บริษัท)

### Q17: K PLUS ของ KBANK มีผู้ใช้กี่ล้านคน?
**Expected Answer:** K PLUS มีผู้ใช้ **22 ล้านคน** โดย 95% ของธุรกรรมทั้งหมดเป็นธุรกรรม Digital  
**Namespace:** company_profiles

### Q18: SCB ก่อตั้งปีอะไร?
**Expected Answer:** SCB (Siam Commercial Bank) ก่อตั้งเมื่อปี **1906** เป็นธนาคารที่เก่าแก่ที่สุดในไทย  
**Namespace:** company_profiles

### Q19: GULF มีกำลังการผลิตไฟฟ้ารวมเท่าไหร่?
**Expected Answer:** GULF มีกำลังการผลิตรวม **12,500 MW** โดย Renewable Mix อยู่ที่ 25%  
**Namespace:** company_profiles

### Q20: BANPU มีเป้าหมายพลังงานสะอาดเท่าไหร่ภายในปี 2030?
**Expected Answer:** BANPU ตั้งเป้าเปลี่ยนผ่านไปสู่พลังงานสะอาด **50%** ภายในปี 2030  
**Namespace:** company_profiles

---

## สรุปตาราง (Summary)

| # | คำถาม | ข้อมูลหลักที่ต้องตรงกัน | Namespace |
|---|-------|--------------------------|-----------|
| 1 | ราคาเป้าหมาย BBL? | THB 185.00 | stock_recommendations |
| 2 | DELTA Div Yield 2026E? | 1.2% | stock_recommendations |
| 3 | หุ้นไหน HOLD? | KBANK | stock_recommendations |
| 4 | EPS PTT 2026E? | THB 4.05 | stock_recommendations |
| 5 | DELTA Datacenter %? | 45% | stock_recommendations |
| 6 | นักวิเคราะห์ BBL? | Napaporn Srisawat | stock_recommendations |
| 7 | NPL BBL 2026E? | 2.8% | stock_recommendations |
| 8 | SET 11 มี.ค.? | 1,438.92 | market_reports |
| 9 | Foreign buy 10 มี.ค.? | THB 2.1B | market_reports |
| 10 | Top Gainers 10 มี.ค.? | DELTA/GULF/AOT | market_reports |
| 11 | CPI ก.พ. 2026? | +1.8% YoY | market_reports |
| 12 | มูลค่าซื้อขาย 11 มี.ค.? | THB 62.5B | market_reports |
| 13 | Circuit Breaker? | 8%/15%/20% | regulations |
| 14 | Settlement? | T+2 | regulations |
| 15 | Tick Size 150 บาท? | THB 1.00 | regulations |
| 16 | Board Lot? | 100 หุ้น | regulations |
| 17 | K PLUS users? | 22 ล้านคน | company_profiles |
| 18 | SCB ก่อตั้ง? | 1906 | company_profiles |
| 19 | GULF capacity? | 12,500 MW | company_profiles |
| 20 | BANPU clean energy? | 50% by 2030 | company_profiles |
