import sys
import structlog
from bond_ytm import BondYieldCalculator

# Настройка логирования для вывода в консоль в читаемом виде
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.dev.ConsoleRenderer()
    ]
)

def run_interactive():
    print("="*50)
    print("Калькулятор доходности облигаций МОЭКС (YTM/YTC)")
    print("="*50)
    
    secid = input("Введите ISIN или SECID облигации (например, SU26207RMFS9): ").strip().upper()
    
    if not secid:
        print("Ошибка: SECID не может быть пустым.")
        return

    calc = BondYieldCalculator()
    
    print(f"\nЗапрашиваю данные для {secid}...")
    
    try:
        result = calc.calculate(secid=secid)
        
        if result.ytm_percent is not None or result.ytm_bid_percent is not None or result.ytm_offer_percent is not None:
            print("\n" + "="*50)
            print(f"Результаты для {result.secid}:")
            print("-" * 50)
            
            if result.ytm_percent is not None:
                print(f"Доходность (Last/Prev): {result.ytm_percent}% годовых")
            if result.ytm_bid_percent is not None:
                print(f"Доходность (Покупка/Bid): {result.ytm_bid_percent}% годовых")
            if result.ytm_offer_percent is not None:
                print(f"Доходность (Продажа/Offer): {result.ytm_offer_percent}% годовых")
                
            print("-" * 50)
            print(f"Грязная цена (для YTM): {result.dirty_price:.2f}")
            print(f"Накопленный купонный доход (НКД): {result.accrued_interest:.2f}")
            
            if result.warning:
                print(f"Предупреждение: {result.warning}")
                
            print("-" * 50)
            print("График ближайших платежей:")
            for flow in result.cashflows[:5]:
                type_str = []
                if flow.is_coupon: type_str.append("Купон")
                if flow.is_amortization: type_str.append("Амортизация")
                type_label = " + ".join(type_str)
                
                print(f"  {flow.date}: {flow.amount:8.2f} ({type_label:15}) | Ост.номинал: {flow.remaining_face_value:8.2f}")
            
            if len(result.cashflows) > 5:
                print(f"  ... и еще {len(result.cashflows) - 5} платежей")
            
            print("="*50)
        else:
            print(f"\n[ОШИБКА РАСЧЁТА]: {result.error_reason}")
            
    except Exception as e:
        print(f"\n[КРИТИЧЕСКАЯ ОШИБКА]: {str(e)}")

if __name__ == "__main__":
    try:
        run_interactive()
    except KeyboardInterrupt:
        print("\nПрограмма завершена пользователем.")
        sys.exit(0)
