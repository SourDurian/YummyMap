# 餐厅数据格式

`data/restaurants.json` 的 `restaurants` 数组中，每项结构如下：

```json
{
  "id": "稳定且唯一的英文短标识",
  "name": "餐厅名",
  "branch": "分店名，可为空",
  "address": "视频中提及并复核后的地址",
  "district": "行政区",
  "cuisine": "菜系或主要品类",
  "pricePerPerson": 58,
  "rating": "recommended",
  "review": "忠实概括视频评价，不添加推测",
  "recommendedDishes": ["菜品一", "菜品二"],
  "visitDate": "2026-01-31",
  "videoUrl": "https://www.bilibili.com/video/BV...",
  "longitude": 114.3055,
  "latitude": 30.5928,
  "verificationStatus": "人工复核",
  "updatedAt": "2026-06-12"
}
```

`rating` 仅允许 `recommended`、`mixed`、`not_recommended`、`unknown`。未知价格和坐标使用 `null`，不要使用推测值。
