"""환율 구간 체크 및 변경 감지 모듈"""
from typing import Dict, Optional

def check_fx_zone(fx_rate: float, fx_rules: Dict) -> Dict:
    """현재 환율이 어느 구간에 속하는지 판단
    
    구간 기준 (투자전략 지침 2026.03 기준):
    - 1,380 미만:        쌓인 원화 전액 환전
    - 1,380 ~ 1,420:    80만원 전액 환전 (정상 구간)
    - 1,420 ~ 1,450:    40만원만 환전 (정상 구간)
    - 1,450 초과:        환전 보류, 원화 현금 적립
    """
    zones = fx_rules['zones']
    baseline = fx_rules['baseline']

    if fx_rate < zones['full_convert']:       # 1,380 미만
        zone = 'full_convert'
        zone_name = '전액 환전 구간'
        action = '쌓인 원화 전액 환전'
    elif fx_rate < zones['normal_full']:      # 1,380 ~ 1,420
        zone = 'normal_full'
        zone_name = '정상 구간 (전액)'
        action = '80만원 전액 환전'
    elif fx_rate < zones['normal_half']:      # 1,420 ~ 1,450
        zone = 'normal_half'
        zone_name = '정상 구간 (절반)'
        action = '40만원만 환전'
    else:                                     # 1,450 초과
        zone = 'pause'
        zone_name = '환전 보류 구간'
        action = '환전 보류, 원화 현금 적립'

    return {
        'zone': zone,
        'zone_name': zone_name,
        'action': action,
        'baseline': baseline,
        'current_rate': fx_rate
    }

def detect_fx_zone_change(prev_rate: float, current_rate: float, fx_rules: Dict) -> Optional[Dict]:
    """환율 구간 변경 감지"""
    prev_zone_info = check_fx_zone(prev_rate, fx_rules)
    current_zone_info = check_fx_zone(current_rate, fx_rules)

    if prev_zone_info['zone'] != current_zone_info['zone']:
        return {
            'prev_zone': prev_zone_info['zone_name'],
            'current_zone': current_zone_info['zone_name'],
            'prev_rate': prev_rate,
            'current_rate': current_rate,
            'action': current_zone_info['action']
        }

    return None