<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card">
      <div class="card-header">
        <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
      </div>
      <div class="budget-slider-row">
        <input
          type="range"
          v-model.number="budget"
          @input="onBudgetInput"
          :min="0"
          :max="maxBudget"
          :step="100"
          class="budget-slider"
        />
        <span class="budget-value">{{ currencySymbol }}{{ budget.toLocaleString() }}</span>
      </div>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendedItems') }}</h3>
        </div>

        <div class="restocking-summary">
          <div class="summary-item">
            <span class="summary-label">{{ t('restocking.totalCost') }}</span>
            <span class="summary-value">{{ currencySymbol }}{{ (recommendations.total_cost || 0).toLocaleString() }}</span>
          </div>
          <div class="summary-item">
            <span class="summary-label">{{ t('restocking.remainingBudget') }}</span>
            <span class="summary-value">{{ currencySymbol }}{{ (recommendations.remaining_budget || 0).toLocaleString() }}</span>
          </div>
        </div>

        <div v-if="recommendedItems.length === 0" class="no-recommendations">
          {{ t('restocking.noRecommendations') }}
        </div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.suggestedQuantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineTotal') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in recommendedItems" :key="item.item_sku">
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ item.item_name }}</td>
                <td>
                  <span :class="['badge', item.trend]">
                    {{ t(`trends.${item.trend}`) }}
                  </span>
                </td>
                <td>{{ item.suggested_quantity }}</td>
                <td>{{ currencySymbol }}{{ item.unit_cost.toLocaleString() }}</td>
                <td><strong>{{ currencySymbol }}{{ item.line_total.toLocaleString() }}</strong></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="place-order-row">
          <button
            class="place-order-btn"
            :disabled="submitting || recommendedItems.length === 0"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placingOrder') : t('restocking.placeOrder') }}
          </button>
        </div>
      </div>

      <div v-if="successMessage" class="success-banner">{{ successMessage }}</div>
      <div v-if="submitError" class="error">{{ submitError }}</div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const currencySymbol = computed(() => {
      return currentCurrency.value === 'JPY' ? '¥' : '$'
    })

    const loading = ref(true)
    const error = ref(null)
    const submitting = ref(false)
    const submitError = ref(null)
    const successMessage = ref(null)

    const maxBudget = ref(10000)
    const budget = ref(5000)
    const recommendations = ref({ recommended_items: [], total_cost: 0, remaining_budget: 0 })

    const recommendedItems = computed(() => recommendations.value.recommended_items || [])

    let debounceTimer = null

    const loadRecommendations = async () => {
      try {
        loading.value = true
        error.value = null
        recommendations.value = await api.getRestockingRecommendations(budget.value)
      } catch (err) {
        error.value = t('restocking.recommendationsError')
        console.error('Failed to load restocking recommendations:', err)
      } finally {
        loading.value = false
      }
    }

    const onBudgetInput = () => {
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        loadRecommendations()
      }, 300)
    }

    const computeMaxBudget = async () => {
      try {
        const forecasts = await api.getDemandForecasts()
        const totalCost = forecasts.reduce((sum, f) => {
          const gap = Math.max(f.forecasted_demand - f.current_demand, 0)
          return sum + gap * f.unit_cost
        }, 0)
        maxBudget.value = Math.ceil(totalCost / 1000) * 1000
        budget.value = Math.round(maxBudget.value / 2)
      } catch (err) {
        console.error('Failed to compute max budget:', err)
      }
    }

    const placeOrder = async () => {
      submitting.value = true
      submitError.value = null
      successMessage.value = null
      try {
        const orderData = {
          budget: budget.value,
          items: recommendedItems.value.map(i => ({
            sku: i.item_sku,
            name: i.item_name,
            quantity: i.suggested_quantity,
            unit_cost: i.unit_cost,
            line_total: i.line_total
          }))
        }
        const order = await api.createRestockingOrder(orderData)
        successMessage.value = t('restocking.orderSuccess', { orderNumber: order.order_number })
        await loadRecommendations()
      } catch (err) {
        submitError.value = t('restocking.orderError')
        console.error('Failed to submit restocking order:', err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(async () => {
      await computeMaxBudget()
      await loadRecommendations()
    })

    return {
      t,
      currencySymbol,
      loading,
      error,
      submitting,
      submitError,
      successMessage,
      maxBudget,
      budget,
      recommendations,
      recommendedItems,
      onBudgetInput,
      placeOrder
    }
  }
}
</script>

<style scoped>
.budget-slider-row {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.budget-slider {
  flex: 1;
  height: 6px;
  border-radius: 3px;
  background: #e2e8f0;
  outline: none;
  accent-color: #2563eb;
  cursor: pointer;
}

.budget-value {
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
  min-width: 120px;
  text-align: right;
}

.restocking-summary {
  display: flex;
  gap: 2rem;
  padding: 0.75rem 0 1rem;
  margin-bottom: 0.5rem;
  border-bottom: 1px solid #f1f5f9;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.summary-label {
  font-size: 0.813rem;
  color: #64748b;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.summary-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
}

.no-recommendations {
  text-align: center;
  padding: 2rem;
  color: #64748b;
  font-size: 0.938rem;
}

.place-order-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 1.25rem;
}

.place-order-btn {
  padding: 0.75rem 1.75rem;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.938rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.success-banner {
  background: #d1fae5;
  border: 1px solid #a7f3d0;
  color: #065f46;
  padding: 1rem;
  border-radius: 8px;
  margin: 1rem 0;
  font-size: 0.938rem;
}
</style>
